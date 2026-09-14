import secrets

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

# from app.services.kb_retriever import retrieve_from_kb  # Commented out to avoid torch import issues
from app.services.generator import generate_answer
from app.services.weekly_quiz_scheduler import send_quiz_to_single_user, process_weekly_quizzes
from app.database.models import get_db, User, WeeklyQuiz, WeeklyQuizAttempt
from app.api.auth_routes import get_current_user
from app.utils.config import ADMIN_API_KEY

router = APIRouter(prefix="/api/v1", tags=["general"])


def require_admin(x_admin_key: Optional[str] = Header(default=None)):
    """Allow the request only if X-Admin-Key matches ADMIN_API_KEY. Disabled when the key is unset."""
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Admin endpoints are disabled")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")


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
    format: str = "brief"       # "brief" | "bullets" | "presentation"
    depth: str = "standard"     # "kid" | "standard" | "exam"
    length: str = "medium"      # "short" | "medium" | "long"
    diagnostic: bool = False    # if True, prepend diagnostic questions


class AnswerResponse(BaseModel):
    question: str
    final_answer: str
    evidence: List[str]
    conf: Optional[str] = None
    caveat: Optional[str] = None
    terms: List[str]
    followups: List[str]


class QuizSubmission(BaseModel):
    answers: Dict[str, str]  # question_index -> selected_answer
    time_taken_seconds: Optional[int] = None


class QuizAttemptResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    score: float
    total_questions: int
    correct_answers: int
    completed_at: str
    answers: List[Dict[str, Any]]


@router.post("/ask", response_model=AnswerResponse)
def ask_question(
    payload: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if current_user.monthly_chats_used >= current_user.monthly_chat_limit:
        raise HTTPException(status_code=429, detail="Monthly chat limit exceeded.")

    # Try to retrieve from knowledge base
    try:
        from app.services.kb_retriever import retrieve_from_kb
        documents = retrieve_from_kb(question, top_k=5)
    except ImportError:
        documents = []
    
    if not documents:
        return AnswerResponse(
            question=question,
            final_answer="Sorry, I could not find relevant information in my knowledge base.",
            evidence=[],
            conf=None,
            caveat=None,
            terms=[],
            followups=[]
        )

    try:
        final_answer, conf, caveat, terms, followups = generate_answer(
            question,
            documents,
            answer_format=payload.format,
            depth=payload.depth,
            length=payload.length,
            diagnostic=payload.diagnostic,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    current_user.monthly_chats_used += 1
    db.commit()

    return AnswerResponse(
        question=question,
        final_answer=final_answer,
        evidence=documents,
        conf=conf,
        caveat=caveat,
        terms=terms,
        followups=followups
    )


# ============ Weekly Quiz Email Endpoints ============

@router.post("/admin/send-weekly-quizzes", dependencies=[Depends(require_admin)])
def trigger_weekly_quizzes():
    """
    Admin endpoint to manually trigger weekly quiz emails for all active users.
    Requires the X-Admin-Key header.

    Returns:
        Dictionary with counts of sent, failed, and skipped emails
    """
    try:
        result = process_weekly_quizzes()
        return {
            "status": "success",
            "message": "Weekly quiz processing completed",
            "details": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process quizzes: {e}")


@router.post("/test/send-quiz-email/{user_id}", dependencies=[Depends(require_admin)])
def test_send_quiz_email(user_id: str):
    """
    Test endpoint to send a quiz email to a specific user.
    Useful for testing email functionality before enabling automatic scheduling.
    
    Args:
        user_id: The UUID of the user to send the quiz to
    
    Returns:
        Status dictionary indicating success or failure
    """
    result = send_quiz_to_single_user(user_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    return result


# ============ Weekly Quiz Endpoints ============

@router.get("/weekly-quiz/{quiz_id}")
def get_weekly_quiz(
    quiz_id: str, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a weekly quiz by ID.
    
    Args:
        quiz_id: The quiz ID
        
    Returns:
        Quiz data with questions (without answers)
    """
    quiz = db.query(WeeklyQuiz).filter(
        WeeklyQuiz.id == quiz_id,
        WeeklyQuiz.user_id == current_user.id
    ).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Check if quiz has expired
    if quiz.expires_at and quiz.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Quiz has expired")
    
    # Check if user has already completed this quiz
    existing_attempt = db.query(WeeklyQuizAttempt).filter(
        WeeklyQuizAttempt.quiz_id == quiz_id,
        WeeklyQuizAttempt.user_id == current_user.id,
        WeeklyQuizAttempt.completed_at.isnot(None)
    ).first()
    
    if existing_attempt:
        raise HTTPException(status_code=409, detail="Quiz already completed")
    
    # Return quiz data without correct answers
    questions = []
    for q in quiz.questions:
        questions.append({
            "question": q.get("question", ""),
            "options": q.get("options", []),
            "difficulty": q.get("difficulty", "medium")
        })
    
    return {
        "quiz_id": quiz.id,
        "title": quiz.title,
        "description": quiz.description,
        "questions": questions,
        "expires_at": quiz.expires_at.isoformat() if quiz.expires_at else None
    }


@router.post("/weekly-quiz/{quiz_id}/submit", response_model=QuizAttemptResponse)
def submit_weekly_quiz(
    quiz_id: str,
    submission: QuizSubmission,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit answers for a weekly quiz.
    
    Args:
        quiz_id: The quiz ID
        submission: User's answers and time taken
        
    Returns:
        Quiz results
    """
    quiz = db.query(WeeklyQuiz).filter(
        WeeklyQuiz.id == quiz_id,
        WeeklyQuiz.user_id == current_user.id
    ).first()
    
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
    
    # Check if quiz has expired
    if quiz.expires_at and quiz.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Quiz has expired")
    
    # Check if user has already completed this quiz
    existing_attempt = db.query(WeeklyQuizAttempt).filter(
        WeeklyQuizAttempt.quiz_id == quiz_id,
        WeeklyQuizAttempt.user_id == current_user.id,
        WeeklyQuizAttempt.completed_at.isnot(None)
    ).first()
    
    if existing_attempt:
        raise HTTPException(status_code=409, detail="Quiz already completed")
    
    # Calculate score
    correct_answers = 0
    total_questions = len(quiz.questions)
    answers_detail = []
    
    for i, question in enumerate(quiz.questions):
        question_key = str(i)
        user_answer = submission.answers.get(question_key, "")
        correct_answer = question.get("correct_answer", "")
        is_correct = user_answer.strip().lower() == correct_answer.strip().lower()
        
        if is_correct:
            correct_answers += 1
            
        answers_detail.append({
            "question_index": i,
            "question": question.get("question", ""),
            "user_answer": user_answer,
            "correct_answer": correct_answer,
            "is_correct": is_correct,
            "explanation": question.get("explanation", "")
        })
    
    score = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
    
    # Create attempt record
    attempt = WeeklyQuizAttempt(
        quiz_id=quiz_id,
        user_id=current_user.id,
        answers=answers_detail,
        score=score,
        total_questions=total_questions,
        correct_answers=correct_answers,
        time_taken_seconds=submission.time_taken_seconds,
        completed_at=datetime.utcnow()
    )
    
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    
    return QuizAttemptResponse(
        attempt_id=attempt.id,
        quiz_id=quiz_id,
        score=score,
        total_questions=total_questions,
        correct_answers=correct_answers,
        completed_at=attempt.completed_at.isoformat(),
        answers=answers_detail
    )


@router.get("/weekly-quiz/{quiz_id}/results")
def get_weekly_quiz_results(
    quiz_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get results for a completed weekly quiz.
    
    Args:
        quiz_id: The quiz ID
        
    Returns:
        Quiz results
    """
    attempt = db.query(WeeklyQuizAttempt).filter(
        WeeklyQuizAttempt.quiz_id == quiz_id,
        WeeklyQuizAttempt.user_id == current_user.id,
        WeeklyQuizAttempt.completed_at.isnot(None)
    ).first()
    
    if not attempt:
        raise HTTPException(status_code=404, detail="Quiz results not found")
    
    return {
        "attempt_id": attempt.id,
        "quiz_id": attempt.quiz_id,
        "score": attempt.score,
        "total_questions": attempt.total_questions,
        "correct_answers": attempt.correct_answers,
        "time_taken_seconds": attempt.time_taken_seconds,
        "completed_at": attempt.completed_at.isoformat(),
        "answers": attempt.answers
    }


@router.get("/weekly-quizzes")
def get_user_weekly_quizzes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all weekly quizzes for the current user.
    
    Returns:
        List of user's weekly quizzes with attempt status
    """
    quizzes = db.query(WeeklyQuiz).filter(
        WeeklyQuiz.user_id == current_user.id
    ).order_by(WeeklyQuiz.created_at.desc()).all()
    
    result = []
    for quiz in quizzes:
        # Check if completed
        attempt = db.query(WeeklyQuizAttempt).filter(
            WeeklyQuizAttempt.quiz_id == quiz.id,
            WeeklyQuizAttempt.user_id == current_user.id,
            WeeklyQuizAttempt.completed_at.isnot(None)
        ).first()
        
        result.append({
            "quiz_id": quiz.id,
            "title": quiz.title,
            "description": quiz.description,
            "week_start_date": quiz.week_start_date.isoformat(),
            "created_at": quiz.created_at.isoformat(),
            "expires_at": quiz.expires_at.isoformat() if quiz.expires_at else None,
            "is_completed": attempt is not None,
            "score": attempt.score if attempt else None,
            "total_questions": len(quiz.questions)
        })
    
    return result