from fastapi import APIRouter, HTTPException, Depends, Query, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
import os
import tempfile

from app.database.models import get_db, Chat, Message, MessageEditHistory, Project, User
from app.api.auth_routes import get_current_user
from app.services.generator import generate_answer, optimize_prompt
from app.services.summarizer import generate_chat_summary
from app.services.document_processor import process_document, select_relevant_passages
from app.services.kb_retriever import retrieve_from_kb
from app.services.question_generator import generate_quiz
from app.services.concept_tracker import update_user_progress, get_user_mastery
from app.services.usage_limits import LimitExceeded, limit_user_action
from app.utils.config import MAX_UPLOAD_MB, ENABLE_PROMPT_REWRITE

router = APIRouter(prefix="/api/v1", tags=["chat"])

# ============ Pydantic Models ============

class QuizRequest(BaseModel):
    chat_id: str
    concept: Optional[str] = "General"

class QuizSubmission(BaseModel):
    concept: str
    results: List[dict]  # [{"question": "...", "is_correct": True}, ...]

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ChatCreate(BaseModel):
    title: Optional[str] = "New Chat"
    project_id: Optional[str] = None
    is_temporary: bool = False
    language: str = "en"

class QuestionRequest(BaseModel):
    question: str
    chat_id: Optional[str] = None
    format: str = "brief"
    depth: str = "standard"
    length: str = "medium"
    diagnostic: bool = False
    language: str = "en"

class SearchQuery(BaseModel):
    query: str
    limit: int = 20

# ============ Project Endpoints ============

@router.post("/projects")
def create_project(
    project: ProjectCreate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    new_project = Project(
        user_id=current_user.id,
        name=project.name,
        description=project.description
    )
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return {"id": new_project.id, "name": new_project.name, "description": new_project.description}


@router.get("/projects")
def list_projects(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    projects = db.query(Project).filter(Project.user_id == current_user.id).order_by(Project.updated_at.desc()).all()
    # One grouped count instead of loading every project's chats (a query per project on a remote DB)
    chat_counts = dict(
        db.query(Chat.project_id, func.count(Chat.id))
        .filter(Chat.project_id.in_([p.id for p in projects]))
        .group_by(Chat.project_id)
        .all()
    ) if projects else {}
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "chat_count": chat_counts.get(p.id, 0),
            "updated_at": p.updated_at.isoformat()
        }
        for p in projects
    ]

# ============ Chat Endpoints ============

@router.post("/chats")
def create_chat(
    chat: ChatCreate, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    new_chat = Chat(
        user_id=current_user.id,
        project_id=chat.project_id,
        title=chat.title,
        is_temporary=chat.is_temporary,
        language=chat.language
    )
    db.add(new_chat)
    db.commit()
    db.refresh(new_chat)
    return {
        "id": new_chat.id,
        "title": new_chat.title,
        "is_temporary": new_chat.is_temporary,
        "project_id": new_chat.project_id
    }


@router.get("/chats")
def list_chats(
    current_user: User = Depends(get_current_user),
    project_id: Optional[str] = None,
    include_temporary: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(Chat).filter(Chat.user_id == current_user.id)
    
    if project_id:
        query = query.filter(Chat.project_id == project_id)
    
    if not include_temporary:
        query = query.filter(Chat.is_temporary == False)
    
    chats = query.order_by(Chat.is_pinned.desc(), Chat.updated_at.desc())\
                 .offset(offset).limit(limit).all()
    # One grouped count instead of loading every chat's messages
    message_counts = dict(
        db.query(Message.chat_id, func.count(Message.id))
        .filter(Message.chat_id.in_([c.id for c in chats]))
        .group_by(Message.chat_id)
        .all()
    ) if chats else {}

    return [
        {
            "id": c.id,
            "title": c.title,
            "summary": c.summary,
            "is_pinned": c.is_pinned,
            "is_temporary": c.is_temporary,
            "project_id": c.project_id,
            "message_count": message_counts.get(c.id, 0),
            "updated_at": c.updated_at.isoformat(),
            "language": c.language
        }
        for c in chats
    ]


@router.get("/chats/pinned")
def get_pinned_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(
        Chat.user_id == current_user.id,
        Chat.is_pinned == True
    ).order_by(Chat.updated_at.desc()).all()
    
    return [
        {
            "id": c.id,
            "title": c.title,
            "updated_at": c.updated_at.isoformat()
        }
        for c in chats
    ]


@router.post("/chats/{chat_id}/pin")
def pin_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pinned_count = db.query(Chat).filter(
        Chat.user_id == current_user.id,
        Chat.is_pinned == True
    ).count()
    
    if pinned_count >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 chats can be pinned. Unpin one first.")
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.is_pinned = True
    db.commit()
    
    return {"status": "pinned"}


@router.post("/chats/{chat_id}/unpin")
def unpin_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat.is_pinned = False
    db.commit()
    return {"status": "unpinned"}


@router.post("/chats/{chat_id}/move")
def move_chat_to_project(
    chat_id: str, 
    project_id: str, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if project_id:
        project = db.query(Project).filter(Project.id == project_id, Project.user_id == current_user.id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
    
    chat.project_id = project_id
    db.commit()
    return {"status": "moved", "project_id": project_id}


@router.get("/chats/{chat_id}")
def get_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    return {
        "id": chat.id,
        "title": chat.title,
        "summary": chat.summary,
        "is_pinned": chat.is_pinned,
        "is_temporary": chat.is_temporary,
        "project_id": chat.project_id,
        "language": chat.language,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "is_edited": m.is_edited,
                "evidence": m.evidence,
                "metadata": m.msg_metadata,
                "created_at": m.created_at.isoformat()
            }
            for m in chat.messages
        ]
    }


@router.delete("/chats/{chat_id}")
def delete_chat(chat_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    db.delete(chat)
    db.commit()
    return {"status": "deleted"}


@router.post("/chats/search")
def search_chats(
    search: SearchQuery, 
    current_user: User = Depends(get_current_user), 
    db: Session = Depends(get_db)
):
    from sqlalchemy import or_, func
    
    chats = db.query(Chat).filter(
        Chat.user_id == current_user.id,
        Chat.is_temporary == False,
        or_(
            Chat.title.ilike(f"%{search.query}%"),
            Chat.summary.ilike(f"%{search.query}%")
        )
    ).limit(search.limit).all()
    
    message_matches = db.query(Message).join(Chat).filter(
        Chat.user_id == current_user.id,
        Message.content.ilike(f"%{search.query}%")
    ).limit(search.limit).all()
    
    chat_ids = {c.id for c in chats}
    for msg in message_matches:
        if msg.chat_id not in chat_ids:
            chats.append(msg.chat)
            chat_ids.add(msg.chat_id)
    
    return [
        {
            "id": c.id,
            "title": c.title,
            "summary": c.summary,
            "updated_at": c.updated_at.isoformat(),
            "match_preview": next(
                (m.content[:100] + "..." for m in c.messages if search.query.lower() in m.content.lower()),
                None
            )
        }
        for c in chats[:search.limit]
    ]

# ============ Message Endpoints ============

@router.post("/chats/{chat_id}/messages")
def add_message_and_respond(
    chat_id: str,
    request: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    limit_user_action(current_user)

    question = request.question.strip()
    target_language = request.language or chat.language
    
    # Check if this is a document-related question (contains document context)
    document_context = ""
    if "Document context:" in question and "Question:" in question:
        # Split the question to extract document context
        parts = question.split("Question:")
        if len(parts) > 1:
            document_context = parts[0].replace("Document context:", "").strip()
            question = parts[1].strip()
    
    optimized_question = optimize_prompt(question) if ENABLE_PROMPT_REWRITE else question

    # Add user message
    user_msg = Message(
        chat_id=chat_id,
        role="user",
        content=question  # Store only the actual question, not the context
    )
    db.add(user_msg)
    
    # Evidence: the most relevant parts of an attached document, otherwise the knowledge base
    if document_context:
        documents = select_relevant_passages(document_context, question)
    else:
        documents = retrieve_from_kb(optimized_question, top_k=5)

    if not documents:
        assistant_content = "Sorry, I could not find relevant information in my knowledge base."
        evidence = []
        msg_meta = {"optimized_question": optimized_question}
    else:
        try:
            final_answer, conf, caveat, terms, followups = generate_answer(
                optimized_question,
                documents,
                answer_format=request.format,
                depth=request.depth,
                length=request.length,
                diagnostic=request.diagnostic,
            )

            assistant_content = final_answer
            evidence = documents
            msg_meta = {
                "conf": conf,
                "caveat": caveat,
                "terms": terms,
                "followups": followups,
                "optimized_question": optimized_question
            }
        except LimitExceeded:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
    
    # Add assistant message
    assistant_msg = Message(
        chat_id=chat_id,
        role="assistant",
        content=assistant_content,
        evidence=evidence,
        msg_metadata=msg_meta
    )
    db.add(assistant_msg)
    
    current_user.monthly_chats_used += 1
    chat.title = question[:50] + ("..." if len(question) > 50 else "")
    chat.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "user_message": {"id": user_msg.id, "content": question},
        "assistant_message": {
            "id": assistant_msg.id,
            "content": assistant_content,
            "evidence": evidence,
            "metadata": msg_meta
        }
    }


@router.put("/messages/{message_id}/edit")
def edit_message(
    message_id: str, 
    edit: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.role != "user":
        raise HTTPException(status_code=400, detail="Only user messages can be edited")
    
    chat = db.query(Chat).filter(Chat.id == message.chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.database.models import MessageEditHistory
    edit_record = MessageEditHistory(
        message_id=message_id,
        previous_content=message.content,
        new_content=edit["content"],
        version=message.version + 1
    )
    db.add(edit_record)
    
    if not message.original_content:
        message.original_content = message.content
    message.content = edit["content"]
    message.is_edited = True
    message.version += 1
    message.edited_at = datetime.utcnow()
    
    subsequent_messages = db.query(Message).filter(
        Message.chat_id == chat.id,
        Message.created_at > message.created_at
    ).all()
    
    for msg in subsequent_messages:
        db.delete(msg)
    
    db.commit()
    
    return {
        "status": "edited",
        "message_id": message_id,
        "new_content": edit["content"],
        "version": message.version,
        "regenerate_required": True
    }

# ============ Summary Endpoints ============

@router.post("/chats/{chat_id}/summarize")
def summarize_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = [{"role": m.role, "content": m.content} for m in chat.messages]
    
    if len(messages) < 2:
        raise HTTPException(status_code=400, detail="Not enough messages to summarize")

    limit_user_action(current_user)
    summary = generate_chat_summary(messages)
    chat.summary = summary
    db.commit()
    
    return {"chat_id": chat_id, "summary": summary}

# ============ Document Processing Endpoints ============

@router.post("/documents/process")
async def process_document_endpoint(
    file: UploadFile = File(...),
    question: str = Form(""),
    current_user: User = Depends(get_current_user)
):
    if not file.filename.lower().endswith(('.pdf', '.docx')):
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")
    
    # Read one byte past the limit so oversized files are rejected without loading them fully
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_MB} MB)")

    await run_in_threadpool(limit_user_action, current_user)

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
        temp_file.write(content)
        temp_file_path = temp_file.name
    
    try:
        # PDF parsing and LLM calls are blocking; keep them off the event loop
        result = await run_in_threadpool(process_document, temp_file_path, question)
        return {
            "filename": file.filename,
            "summary": result.get("summary", ""),
            "full_text": result.get("full_text", ""),
            "answer": result.get("answer", "") if question else None
        }
    finally:
        os.unlink(temp_file_path)

# ============ Temporary Chat Cleanup ============

@router.delete("/chats/temporary/cleanup")
def cleanup_temporary_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deleted = db.query(Chat).filter(
        Chat.user_id == current_user.id,
        Chat.is_temporary == True
    ).delete()
    
    db.commit()
    return {"deleted_count": deleted}


# ============ Quiz Endpoints ============

@router.post("/chats/{chat_id}/quiz")
def generate_chat_quiz(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get the last assistant message
    last_msg = db.query(Message).filter(
        Message.chat_id == chat_id,
        Message.role == "assistant"
    ).order_by(Message.created_at.desc()).first()
    
    if not last_msg:
        raise HTTPException(status_code=400, detail="No assistant message found to generate quiz from")
    
    # Generate quiz
    limit_user_action(current_user)
    quiz = generate_quiz(last_msg.content, num_questions=5)
    return {"quiz": quiz}

@router.post("/quiz/submit")
def submit_quiz_results(
    submission: QuizSubmission,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    total_correct = 0
    total_questions = len(submission.results)
    
    for result in submission.results:
        is_correct = result.get("is_correct", False)
        if is_correct:
            total_correct += 1
        
        update_user_progress(
            user_id=current_user.id,
            concept=submission.concept,
            is_correct=is_correct,
            db=db
        )
    
    return {
        "status": "graded",
        "score": f"{total_correct}/{total_questions}",
        "percentage": (total_correct / total_questions) * 100 if total_questions > 0 else 0,
        "concept": submission.concept
    }

@router.get("/progress")
def get_user_progress(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    progress = get_user_mastery(current_user.id, db)
    return [
        {
            "concept": p.concept,
            "mastery_level": p.mastery_level,
            "questions_answered": p.questions_answered,
            "correct_answers": p.correct_answers,
            "accuracy": (p.correct_answers / p.questions_answered * 100) if p.questions_answered > 0 else 0
        }
        for p in progress
    ]
