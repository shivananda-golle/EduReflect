import os
import streamlit as st
import requests
from io import BytesIO
from datetime import datetime
import json

# Import ReportLab components
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
API_BASE = f"{BACKEND_URL}/api/v1"

# Request timeouts (seconds)
DEFAULT_API_TIMEOUT = float(os.getenv("DEFAULT_API_TIMEOUT", "30"))
LONG_API_TIMEOUT = float(os.getenv("LONG_API_TIMEOUT", "300"))


def _pick_timeout(endpoint: str, files: bool = False) -> float:
    """Use longer timeouts for endpoints that may take time (model downloads, generation)."""
    if files:
        return LONG_API_TIMEOUT
    slow_markers = (
        "/messages",
        "/documents/process",
        "/summarize",
        "/quiz",
        "/weekly-quiz",
    )
    if any(m in endpoint for m in slow_markers):
        return LONG_API_TIMEOUT
    return DEFAULT_API_TIMEOUT

st.set_page_config(page_title="EduReflect", page_icon="📘", layout="wide")

# ============ Session State Initialization ============
def init_session_state():
    defaults = {
        "authenticated": False,
        "user": None,
        "token": None,
        "current_chat_id": None,
        "current_project_id": None,
        "messages": [],
        "is_temporary": False,
        "editing_message_id": None,
        "editing_content": "",
        "selected_language": "en",
        "answer_format": "brief",
        "depth": "standard",
        "length": "medium",
        "diagnostic_mode": False,
        "show_evidence": False,
        "minimal_mode": False,
        "uploaded_documents": [],
        "pdf_data": None,
        "show_pdf_download": False,
        "clear_input": False,
        "page": "login",
        "current_quiz": None,
        "quiz_submitted": False,
        "quiz_score": None,
        "quiz_user_answers": None,
        "quiz_pdf_data": None,
        "show_quiz_pdf_download": False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()

# ============ Auth Session Helpers ============
def force_logout(message: str = "Session expired. Please log in again."):
    """Clear auth-related session state and return to login page."""
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.token = None
    st.session_state.page = "login"
    st.session_state.current_chat_id = None
    st.session_state.current_project_id = None
    st.session_state.messages = []
    st.session_state.uploaded_documents = []
    st.session_state.pdf_data = None
    st.session_state.show_pdf_download = False
    st.warning(message)
    st.rerun()

# ============ PDF Export with ReportLab ============
def export_pdf(messages):
    """Generate PDF using ReportLab (professional quality)"""
    buffer = BytesIO()
    
    # Create document
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Define custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.gray
    )
    
    user_style = ParagraphStyle(
        'UserMessage',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        leftIndent=20,
        borderWidth=1,
        borderColor=colors.lightblue,
        borderPadding=5,
        backgroundColor=colors.lightblue
    )
    
    assistant_style = ParagraphStyle(
        'AssistantMessage',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        leftIndent=20,
        borderWidth=1,
        borderColor=colors.lightgreen,
        borderPadding=5,
        backgroundColor=colors.lightgreen
    )
    
    # Build PDF content
    content = []
    
    # Title
    content.append(Paragraph("EduReflect Chat Export", title_style))
    
    # Subtitle with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content.append(Paragraph(f"Generated on {timestamp}", subtitle_style))
    
    content.append(Spacer(1, 20))
    
    if not messages:
        content.append(Paragraph("No messages to export.", styles['Normal']))
    else:
        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            message_content = msg.get("content", "")
            
            if not message_content:
                message_content = "[Empty message]"
            
            # Escape HTML entities and handle special characters
            safe_content = message_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            # Add role label
            role_label = "👤 User:" if role == "user" else "🤖 Assistant:"
            content.append(Paragraph(f"<b>{role_label}</b>", styles['Heading3']))
            
            # Add message content
            if role == "user":
                content.append(Paragraph(safe_content, user_style))
            else:
                content.append(Paragraph(safe_content, assistant_style))
            
            content.append(Spacer(1, 10))
    
    # Build PDF
    doc.build(content)
    
    # Get PDF data
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    print(f"DEBUG: ReportLab PDF generated with {len(pdf_data)} bytes")
    return pdf_data

# ============ Quiz Report PDF Export ============
def export_quiz_report(concept: str, percentage: float, quiz_items: list, student_name: str = ""):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'QuizTitle',
        parent=styles['Heading1'],
        fontSize=22,
        spaceAfter=20,
        alignment=TA_CENTER,
        textColor=colors.darkblue
    )
    subtitle_style = ParagraphStyle(
        'QuizSubtitle',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=10,
        alignment=TA_CENTER,
        textColor=colors.gray
    )
    section_header = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading3'],
        fontSize=14,
        textColor=colors.black,
        spaceAfter=8
    )
    q_style = ParagraphStyle(
        'Question',
        parent=styles['Normal'],
        fontSize=11,
        spaceAfter=6
    )
    correct_style = ParagraphStyle(
        'Correct',
        parent=styles['Normal'],
        textColor=colors.green,
        fontSize=10,
        spaceAfter=4
    )
    incorrect_style = ParagraphStyle(
        'Incorrect',
        parent=styles['Normal'],
        textColor=colors.red,
        fontSize=10,
        spaceAfter=4
    )
    expl_style = ParagraphStyle(
        'Explanation',
        parent=styles['Italic'],
        fontSize=10,
        textColor=colors.gray
    )
    
    content = []
    content.append(Paragraph("EduReflect Quiz Report", title_style))
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content.append(Paragraph(f"Generated on {timestamp}", subtitle_style))
    content.append(Spacer(1, 12))
    
    total_questions = len(quiz_items)
    total_correct = sum(1 for item in quiz_items if item.get("is_correct"))
    marks_100 = int(round(percentage))
    
    content.append(Paragraph("Summary", section_header))
    content.append(Paragraph(f"Concept: {concept}", styles['Normal']))
    if student_name:
        content.append(Paragraph(f"Student: {student_name}", styles['Normal']))
    content.append(Paragraph(f"Score: {total_correct}/{total_questions} ({percentage:.1f}%)", styles['Normal']))
    content.append(Paragraph(f"Marks: {marks_100}/100", styles['Normal']))
    content.append(Spacer(1, 12))
    
    content.append(Paragraph("Questions and Answers", section_header))
    
    for idx, item in enumerate(quiz_items, start=1):
        question_text = item.get("question", "")
        user_answer = item.get("selected_answer", "")
        correct_answer = item.get("correct_answer", "")
        explanation = item.get("explanation", "")
        difficulty = item.get("difficulty", "")
        is_correct = item.get("is_correct", False)
        
        safe_q = question_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        content.append(Paragraph(f"{idx}. {safe_q}", q_style))
        content.append(Paragraph(f"Difficulty: {difficulty or 'N/A'}", styles['Normal']))
        if is_correct:
            content.append(Paragraph(f"Your Answer: {user_answer}", correct_style))
        else:
            content.append(Paragraph(f"Your Answer: {user_answer}", incorrect_style))
        content.append(Paragraph(f"Correct Answer: {correct_answer}", styles['Normal']))
        if explanation:
            safe_expl = explanation.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            content.append(Paragraph(f"Explanation: {safe_expl}", expl_style))
        content.append(Spacer(1, 8))
    
    doc.build(content)
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ============ Authentication Functions ============
def api_post(endpoint, data=None, auth=True, files=None):
    headers = {"Content-Type": "application/json"} if not files else {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    
    try:
        if files:
            response = requests.post(
                f"{API_BASE}{endpoint}",
                files=files,
                data=data,
                headers=headers,
                timeout=_pick_timeout(endpoint, files=True),
            )
        else:
            response = requests.post(
                f"{API_BASE}{endpoint}",
                json=data,
                headers=headers,
                timeout=_pick_timeout(endpoint, files=False),
            )

        if auth and response.status_code == 401:
            force_logout()

        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        st.error(
            "Request timed out. The backend may be loading models for the first time. "
            "Please wait a bit and try again."
        )
        return None
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

def api_get(endpoint, auth=True):
    headers = {}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    
    try:
        resp = requests.get(
            f"{API_BASE}{endpoint}",
            headers=headers,
            timeout=_pick_timeout(endpoint, files=False),
        )

        if auth and resp.status_code == 401:
            force_logout()

        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        st.error(
            "Request timed out. The backend may be busy/starting up. "
            "Please wait a bit and try again."
        )
        return None
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

def api_put(endpoint, data=None, auth=True):
    headers = {"Content-Type": "application/json"}
    if auth and st.session_state.token:
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    
    try:
        resp = requests.put(
            f"{API_BASE}{endpoint}",
            json=data,
            headers=headers,
            timeout=_pick_timeout(endpoint, files=False),
        )

        if auth and resp.status_code == 401:
            force_logout()

        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        st.error("Request timed out. Please try again.")
        return None
    except Exception as e:
        st.error(f"API Error: {e}")
        return None

def login_user(username, password):
    data = {"username": username, "password": password}
    result = api_post("/auth/login-json", data, auth=False)
    if result and "access_token" in result:
        st.session_state.token = result["access_token"]
        st.session_state.authenticated = True
        user_info = api_get("/auth/me")
        if user_info:
            st.session_state.user = user_info
            st.session_state.page = "main"
            return True
    return False

def signup_user(username, email, password, full_name=""):
    data = {
        "username": username,
        "email": email,
        "password": password,
        "full_name": full_name
    }
    result = api_post("/auth/register", data, auth=False)
    if result:
        st.success("Account created successfully! Please login.")
        st.session_state.page = "login"
        return True
    return False

def logout_user():
    st.session_state.authenticated = False
    st.session_state.user = None
    st.session_state.token = None
    st.session_state.page = "login"
    st.session_state.messages = []
    st.session_state.uploaded_documents = []
    st.session_state.pdf_data = None
    st.session_state.show_pdf_download = False

# ============ Auth UI Components ============
def show_login_page():
    st.title("📘 EduReflect - Login")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Welcome Back!")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Login", use_container_width=True):
                if login_user(username, password):
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        
        st.divider()
        if st.button("Don't have an account? Sign up", use_container_width=True):
            st.session_state.page = "signup"
            st.rerun()

def show_signup_page():
    st.title("📘 EduReflect - Sign Up")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Create Your Account")
        
        with st.form("signup_form"):
            username = st.text_input("Username")
            email = st.text_input("Email")
            full_name = st.text_input("Full Name (Optional)")
            password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Confirm Password", type="password")
            
            if st.form_submit_button("Create Account", use_container_width=True):
                if password != confirm_password:
                    st.error("Passwords don't match")
                else:
                    if signup_user(username, email, password, full_name):
                        pass
                    else:
                        st.error("Registration failed")
        
        st.divider()
        if st.button("Already have an account? Login", use_container_width=True):
            st.session_state.page = "login"
            st.rerun()

def show_subscription_info():
    if not st.session_state.user:
        return
    
    sub = st.session_state.user.get("subscription", {})
    tier_colors = {"free": "🆓", "basic": "💎", "premium": "👑"}
    
    st.markdown(f"**{tier_colors.get(sub.get('tier', 'free'), '🆓')} {sub.get('tier', 'free').title()} Plan**")
    
    if sub.get("active"):
        st.markdown(f"✅ Active | 💬 {sub.get('remaining_chats', 0)} chats left this month")
        if sub.get("expires_at"):
            st.caption(f"Expires: {sub.get('expires_at')[:10]}")
    else:
        st.warning("⚠️ Subscription expired or inactive")
        
        with st.expander("🚀 Upgrade Your Plan"):
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("🆓 Free\n50 chats/month", use_container_width=True):
                    upgrade_subscription("free")
            with col2:
                if st.button("💎 Basic\n500 chats/month", use_container_width=True):
                    upgrade_subscription("basic")
            with col3:
                if st.button("👑 Premium\n2000 chats/month", use_container_width=True):
                    upgrade_subscription("premium")

def upgrade_subscription(tier):
    result = api_post("/auth/subscription", {"tier": tier, "duration_months": 1})
    if result:
        st.success(f"Upgraded to {tier.title()} plan!")
        user_info = api_get("/auth/me")
        if user_info:
            st.session_state.user = user_info
        st.rerun()

# ============ Chat Management Functions ============
def create_new_chat(is_temporary=False, project_id=None):
    data = {
        "title": "New Chat",
        "is_temporary": is_temporary,
        "project_id": project_id,
        "language": st.session_state.selected_language
    }
    result = api_post("/chats", data)
    if result:
        st.session_state.current_chat_id = result["id"]
        st.session_state.is_temporary = is_temporary
        st.session_state.messages = []
        st.session_state.uploaded_documents = []
        st.session_state.pdf_data = None
        st.session_state.show_pdf_download = False
    return result

def load_chat(chat_id):
    result = api_get(f"/chats/{chat_id}")
    if result:
        st.session_state.current_chat_id = chat_id
        st.session_state.messages = result.get("messages", [])
        st.session_state.is_temporary = result.get("is_temporary", False)
        st.session_state.pdf_data = None
        st.session_state.show_pdf_download = False
    return result

def send_message(question, document_context=""):
    if not st.session_state.current_chat_id:
        create_new_chat(is_temporary=st.session_state.is_temporary)
    
    full_question = question
    if document_context:
        full_question = f"Document context:\n{document_context}\n\nQuestion: {question}"
    
    data = {
        "question": full_question,
        "format": st.session_state.answer_format,
        "depth": st.session_state.depth,
        "length": st.session_state.length,
        "diagnostic": st.session_state.diagnostic_mode,
        "language": st.session_state.selected_language
    }
    
    result = api_post(f"/chats/{st.session_state.current_chat_id}/messages", data)
    if result:
        load_chat(st.session_state.current_chat_id)
    return result

def edit_message(message_id, new_content):
    result = api_put(f"/messages/{message_id}/edit", {"content": new_content})
    if result and result.get("regenerate_required"):
        send_message(new_content)
    return result

def pin_chat(chat_id):
    return api_post(f"/chats/{chat_id}/pin")

def unpin_chat(chat_id):
    return api_post(f"/chats/{chat_id}/unpin")

def search_chats(query):
    return api_post("/chats/search", {"query": query, "limit": 20})

def summarize_current_chat():
    if st.session_state.current_chat_id:
        return api_post(f"/chats/{st.session_state.current_chat_id}/summarize")
    return None

def generate_quiz():
    if st.session_state.current_chat_id:
        with st.spinner("Generating quiz..."):
            result = api_post(f"/chats/{st.session_state.current_chat_id}/quiz")
            if result and "quiz" in result:
                st.session_state.current_quiz = result["quiz"]
                st.session_state.quiz_submitted = False
                st.session_state.quiz_score = None
                return True
    return False

def submit_quiz_answers(results):
    data = {
        "concept": "Chat Session " + st.session_state.current_chat_id[:8],
        "results": results
    }
    result = api_post("/quiz/submit", data)
    if result:
        st.session_state.quiz_score = result
        st.session_state.quiz_submitted = True
    return result

# ============ Quiz Grading Helpers ============
def _normalize_text(s: str) -> str:
    if not s:
        return ""
    return "".join(ch.lower() for ch in s.strip())

def _map_correct_answer(q: dict):
    options = q.get("options", []) or []
    correct_text = q.get("correct_answer", "") or ""
    correct_index = q.get("correct_answer_index", None)
    
    if isinstance(correct_index, int) and 0 <= correct_index < len(options):
        return options[correct_index], correct_index
    
    ct = correct_text.strip()
    if not ct and options:
        return options[0], 0
    
    # Letter-based forms: "A", "B", "Option A", "A)", "A.", etc.
    letter_map = {"a": 0, "b": 1, "c": 2, "d": 3}
    if len(ct) >= 1:
        first = ct[0].lower()
        if first in letter_map and letter_map[first] < len(options):
            idx = letter_map[first]
            return options[idx], idx
    if ct.lower().startswith("option "):
        maybe = ct.lower().replace("option ", "").strip()[:1]
        if maybe in letter_map and letter_map[maybe] < len(options):
            idx = letter_map[maybe]
            return options[idx], idx
    
    # Exact match ignoring case/whitespace
    nct = _normalize_text(ct)
    for i, opt in enumerate(options):
        if _normalize_text(opt) == nct:
            return opt, i
    
    # Substring fallback
    for i, opt in enumerate(options):
        no = _normalize_text(opt)
        if nct and (nct in no or no in nct):
            return opt, i
    
    # Default to first option if unresolved
    return options[0] if options else "", 0

def process_uploaded_file(file):
    files = {"file": (file.name, file.getvalue(), file.type)}
    result = api_post("/documents/process", {}, files=files)
    if result:
        return {
            "filename": result.get("filename", file.name),
            "content": result.get("summary", ""),
            "full_text": result.get("full_text", "")
        }
    return None

# ============ Project Management Functions ============
def create_project(name, description=""):
    return api_post("/projects", {"name": name, "description": description})

def get_projects():
    return api_get("/projects")

def move_chat_to_project(chat_id, project_id):
    return api_post(f"/chats/{chat_id}/move", {"project_id": project_id})

# ============ Weekly Quiz Functions ============
def get_weekly_quiz(quiz_id):
    return api_get(f"/weekly-quiz/{quiz_id}")

def submit_weekly_quiz(quiz_id, answers, time_taken=None):
    data = {"answers": answers}
    if time_taken:
        data["time_taken_seconds"] = time_taken
    return api_post(f"/weekly-quiz/{quiz_id}/submit", data)

def get_weekly_quiz_results(quiz_id):
    return api_get(f"/weekly-quiz/{quiz_id}/results")

# ============ Weekly Quiz Page ============
def show_weekly_quiz_page(quiz_id):
    st.title("📘 Weekly EduReflect Quiz")
    
    # Try to get quiz data
    quiz_data = get_weekly_quiz(quiz_id)
    
    if not quiz_data:
        # Check if it's because quiz is completed
        results_data = get_weekly_quiz_results(quiz_id)
        if results_data:
            # Show results
            st.subheader("Quiz Results")
            score = results_data.get("score", 0)
            total_questions = results_data.get("total_questions", 0)
            correct_answers = results_data.get("correct_answers", 0)
            
            st.success(f"Quiz Completed! Score: {score:.1f}% ({correct_answers}/{total_questions})")
            
            st.markdown("**Detailed Results:**")
            for answer in results_data.get("answers", []):
                question_num = answer.get("question_index", 0) + 1
                is_correct = answer.get("is_correct", False)
                color = "green" if is_correct else "red"
                
                st.markdown(f"**Question {question_num}:** {answer.get('question', '')}")
                st.markdown(f"<span style='color:{color}'>Your Answer: {answer.get('user_answer', '')}</span>", unsafe_allow_html=True)
                st.write(f"Correct Answer: {answer.get('correct_answer', '')}")
                if answer.get("explanation"):
                    st.caption(f"Explanation: {answer.get('explanation')}")
                st.markdown("---")
            
            # PDF Export
            if st.button("📄 Generate Quiz Report (PDF)"):
                with st.spinner("Preparing PDF report..."):
                    pdf_bytes = export_quiz_report(
                        concept="Weekly EduReflect Quiz",
                        percentage=score,
                        quiz_items=results_data.get("answers", []),
                        student_name=st.session_state.user.get("username", "Student")
                    )
                    st.session_state.quiz_pdf_data = pdf_bytes
                    st.session_state.show_quiz_pdf_download = True
                    st.success("Report generated!")
            
            if st.session_state.show_quiz_pdf_download and st.session_state.quiz_pdf_data:
                fname = f"EduReflect_Weekly_Quiz_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                st.download_button(
                    label="⬇️ Download Quiz Report",
                    data=st.session_state.quiz_pdf_data,
                    file_name=fname,
                    mime="application/pdf"
                )
            
            if st.button("Return to EduReflect"):
                st.query_params.clear()
                st.rerun()
        else:
            st.error("Quiz not found or access denied.")
        return
    
    # Show the quiz
    st.markdown(f"**{quiz_data.get('title', 'Weekly Quiz')}**")
    st.markdown(f"*{quiz_data.get('description', '')}*")
    
    expires_at = quiz_data.get('expires_at')
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            st.info(f"⏰ Quiz expires: {expiry.strftime('%Y-%m-%d %H:%M')}")
        except:
            pass
    
    questions = quiz_data.get("questions", [])
    
    if not questions:
        st.error("No questions found in this quiz.")
        return
    
    # Quiz form
    with st.form("weekly_quiz_form"):
        answers = {}
        start_time = datetime.now()
        
        for i, q in enumerate(questions):
            question_text = q.get("question", "")
            options = q.get("options", [])
            difficulty = q.get("difficulty", "medium")
            
            # Difficulty emoji
            diff_emoji = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(difficulty.lower(), "🟡")
            
            st.markdown(f"**Question {i+1}** {diff_emoji} {difficulty.title()}")
            st.markdown(question_text)
            
            selected = st.radio(
                f"Select your answer:",
                options,
                key=f"q_{i}",
                index=None,
                label_visibility="collapsed"
            )
            answers[str(i)] = selected
            st.markdown("---")
        
        submitted = st.form_submit_button("Submit Quiz", use_container_width=True)
        
        if submitted:
            # Check if all questions answered
            unanswered = [i for i, ans in answers.items() if not ans]
            if unanswered:
                st.error(f"Please answer all questions. Unanswered: {', '.join([str(i+1) for i in unanswered])}")
            else:
                # Calculate time taken
                time_taken = int((datetime.now() - start_time).total_seconds())
                
                # Submit answers
                with st.spinner("Submitting quiz..."):
                    result = submit_weekly_quiz(quiz_id, answers, time_taken)
                
                if result:
                    st.success("Quiz submitted successfully!")
                    st.rerun()
                else:
                    st.error("Failed to submit quiz. Please try again.")
    
    if st.button("Cancel"):
        st.query_params.clear()
        st.rerun()

def get_user_weekly_quizzes():
    return api_get("/weekly-quizzes")

def show_weekly_quiz_page(quiz_id):
    """Display a weekly quiz page"""
    st.title("📘 Weekly EduReflect Quiz")
    
    # Get quiz data
    quiz_data = get_weekly_quiz(quiz_id)
    
    if not quiz_data:
        st.error("Quiz not found or access denied.")
        return
    
    st.markdown(f"## {quiz_data['title']}")
    if quiz_data.get('description'):
        st.markdown(quiz_data['description'])
    
    if quiz_data.get('expires_at'):
        st.info(f"⏰ Quiz expires: {quiz_data['expires_at']}")
    
    # Quiz form
    with st.form(key=f"quiz_form_{quiz_id}"):
        user_answers = {}
        start_time = datetime.now()
        
        for i, question in enumerate(quiz_data['questions']):
            st.markdown(f"### Question {i+1}")
            st.markdown(question['question'])
            
            # Display difficulty
            difficulty = question.get('difficulty', 'medium')
            difficulty_colors = {
                'easy': '🟢',
                'medium': '🟡', 
                'hard': '🔴'
            }
            st.caption(f"{difficulty_colors.get(difficulty, '🟡')} {difficulty.capitalize()}")
            
            # Radio buttons for options
            options = question['options']
            user_answers[str(i)] = st.radio(
                f"Select your answer for question {i+1}:",
                options,
                key=f"q_{i}",
                label_visibility="collapsed"
            )
        
        submitted = st.form_submit_button("Submit Quiz", type="primary")
    
    # Handle submission OUTSIDE the form
    if submitted:
        # Calculate time taken
        end_time = datetime.now()
        time_taken = int((end_time - start_time).total_seconds())
        
        # Submit answers
        with st.spinner("Submitting your quiz..."):
            result = submit_weekly_quiz(quiz_id, user_answers, time_taken)
        
        if result:
            st.success("Quiz submitted successfully!")
            st.balloons()
            
            # Display results
            st.markdown("## 📊 Your Results")
            st.metric("Score", f"{result['score']:.1f}%")
            st.metric("Correct Answers", f"{result['correct_answers']}/{result['total_questions']}")
            
            if result.get('time_taken_seconds'):
                minutes = result['time_taken_seconds'] // 60
                seconds = result['time_taken_seconds'] % 60
                st.metric("Time Taken", f"{minutes}:{seconds:02d}")
            
            # Show detailed breakdown
            st.markdown("### Question Breakdown")
            for answer in result['answers']:
                with st.expander(f"Question {answer['question_index'] + 1}: {'✅' if answer['is_correct'] else '❌'}"):
                    st.markdown(f"**Question:** {answer['question']}")
                    st.markdown(f"**Your Answer:** {answer['user_answer']}")
                    st.markdown(f"**Correct Answer:** {answer['correct_answer']}")
                    if answer.get('explanation'):
                        st.markdown(f"**Explanation:** {answer['explanation']}")
            
            # Export option - now outside the form
            if st.button("📄 Export Results as PDF"):
                pdf_data = export_quiz_report(
                    "Weekly EduReflect Quiz",
                    result['score'],
                    result['answers'],
                    st.session_state.user.get('username', 'Student')
                )
                if pdf_data:
                    st.download_button(
                        label="Download PDF Report",
                        data=pdf_data,
                        file_name=f"weekly_quiz_results_{quiz_id[:8]}.pdf",
                        mime="application/pdf"
                    )
        else:
            st.error("Failed to submit quiz. Please try again.")

# ============ Main App Logic ============
# Check for quiz URL parameters
query_params = st.query_params
if "quiz" in query_params:
    quiz_id = query_params["quiz"]
    if st.session_state.authenticated:
        show_weekly_quiz_page(quiz_id)
        st.stop()
    else:
        st.warning("Please log in to access your quiz.")
        show_login_page()
        st.stop()

if not st.session_state.authenticated:
    if st.session_state.page == "login":
        show_login_page()
    elif st.session_state.page == "signup":
        show_signup_page()
else:
    st.title("📘 EduReflect Chat")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.session_state.user:
            st.markdown(f"Welcome, **{st.session_state.user.get('username', 'User')}**!")
    with col2:
        if st.button("Logout", use_container_width=True):
            logout_user()
            st.rerun()
    
    show_subscription_info()
    st.divider()
    
    with st.sidebar:
        st.title("📘 EduReflect")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("➕ New Chat", use_container_width=True):
                create_new_chat(is_temporary=False)
                st.rerun()
        with col2:
            if st.button("⏳ Temp Chat", use_container_width=True, help="Temporary chat won't be saved"):
                create_new_chat(is_temporary=True)
                st.rerun()
        
        st.divider()
        
        with st.expander("📁 Projects", expanded=False):
            projects = get_projects() or []
            
            new_project_name = st.text_input("New project name", key="new_project_input")
            if st.button("Create Project") and new_project_name:
                create_project(new_project_name)
                st.rerun()
            
            for project in projects:
                if st.button(f"📁 {project['name']} ({project['chat_count']})", key=f"proj_{project['id']}"):
                    st.session_state.current_project_id = project["id"]
                    st.rerun()
        
        st.divider()
        
        search_query = st.text_input("🔍 Search chats", key="search_input")
        if search_query:
            search_results = search_chats(search_query)
            if search_results:
                st.markdown("**Search Results:**")
                for chat in search_results:
                    if st.button(f"📝 {chat['title'][:30]}...", key=f"search_{chat['id']}"):
                        load_chat(chat["id"])
                        st.rerun()
        
        st.divider()
        
        st.markdown("**📌 Pinned Chats**")
        pinned = api_get("/chats/pinned") or []
        for chat in pinned:
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(f"📌 {chat['title'][:25]}...", key=f"pinned_{chat['id']}"):
                    load_chat(chat["id"])
                    st.rerun()
            with col2:
                if st.button("✖", key=f"unpin_{chat['id']}", help="Unpin"):
                    unpin_chat(chat["id"])
                    st.rerun()
        
        if len(pinned) < 3 and st.session_state.current_chat_id:
            if st.button("📌 Pin Current Chat"):
                pin_chat(st.session_state.current_chat_id)
                st.rerun()
        
        st.divider()
        
        st.markdown("**Recent Chats**")
        chats = api_get("/chats?limit=10") or []
        for chat in chats[:10]:
            if chat.get("is_pinned"):
                continue
            if st.button(f" {chat['title'][:30]}...", key=f"chat_{chat['id']}"):
                load_chat(chat["id"])
                st.rerun()
        
        st.divider()
        
        st.markdown("**⚙️ Settings**")
        
        st.radio(
            "Answer format",
            options=["brief", "bullets", "presentation"],
            format_func=lambda x: {"brief": "Brief", "bullets": "Bullets", "presentation": "Presentation"}[x],
            key="answer_format"
        )
        
        st.checkbox("Show Evidence", key="show_evidence")
        
        st.divider()
        
        # Weekly Quizzes Section
        with st.expander("📘 Weekly Quizzes", expanded=False):
            weekly_quizzes = get_user_weekly_quizzes() or []
            
            if not weekly_quizzes:
                st.caption("No weekly quizzes yet. Check back next week!")
            else:
                for quiz in weekly_quizzes:
                    status_icon = "✅" if quiz["is_completed"] else "⏳"
                    score_text = f" - {quiz['score']:.1f}%" if quiz["is_completed"] else ""
                    
                    if st.button(f"{status_icon} {quiz['title'][:25]}{score_text}", 
                               key=f"quiz_{quiz['quiz_id']}"):
                        # Navigate to quiz page
                        st.query_params["quiz"] = quiz["quiz_id"]
                        st.rerun()
        
        st.divider()
        
        with st.expander("🛠 Prompt Optimization Examples", expanded=False):
            examples = [
                ("hey can u explain that thing about diff eqns?", "Explain the basic idea of ordinary differential equations with a simple example."),
                ("solve it like before but shorter", "Solve dy/dx = 3y with y(0) = 2."),
                ("what’s that ozone thing again", "Describe the ozone layer and how it protects ecosystems from ultraviolet radiation."),
                ("so plastics recycling um is it bad??", "Explain how plastics are recycled and the environmental impacts."),
                ("tell me about that war we talked about", "Summarize the causes and major events of World War I."),
                ("who was that guy with the reforms?", "Identify and describe key reforms introduced by Napoleon Bonaparte."),
                ("make it faster pls", "Propose two ways to optimize performance of a Python function that processes a large list of numbers."),
                ("that error again, the one with import", "Explain common causes of Python ModuleNotFoundError and how to fix them."),
                ("answer based on that pdf, you know the one", "Using the attached PDF, summarize the main learning objectives in the ecosystems chapter."),
                ("compare them and say which is better", "Compare solar and wind energy for a coastal city in cost, reliability, and environmental impact, and state which is better.")
            ]
            for given, optimized in examples:
                st.markdown("**Given:** " + given)
                st.markdown("**Optimized:** " + optimized)
                st.markdown("---")
        
        # PDF Export Button
        if st.session_state.messages:
            if st.button("📄 Export as PDF", use_container_width=True):
                with st.spinner("Generating PDF..."):
                    pdf_bytes = export_pdf(st.session_state.messages)
                    if pdf_bytes:
                        st.session_state.pdf_data = pdf_bytes
                        st.session_state.show_pdf_download = True
                        st.success("PDF generated successfully!")
                        st.rerun()
        
        # PDF Download Button (shown after generation)
        if st.session_state.show_pdf_download and st.session_state.pdf_data:
            st.download_button(
                label="Download PDF",
                data=st.session_state.pdf_data,
                file_name="edureflect_chat.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        if st.session_state.messages and len(st.session_state.messages) >= 2:
            if st.button("📋 Generate Summary"):
                result = summarize_current_chat()
                if result:
                    st.success(f"Summary: {result.get('summary', '')}")

    # ============ Main Chat Area ============
    if st.session_state.is_temporary:
        st.warning("⏳ This is a temporary chat and won't be saved to history.")

    # Show uploaded documents
    if st.session_state.uploaded_documents:
        with st.expander("📎 Attached Documents", expanded=False):
            for i, doc in enumerate(st.session_state.uploaded_documents):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"📄 **{doc['filename']}**")
                    st.caption(f"Content preview: {doc['content'][:200]}...")
                with col2:
                    if st.button("❌", key=f"remove_doc_{i}"):
                        st.session_state.uploaded_documents.pop(i)
                        st.rerun()

    # Display messages
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if st.session_state.editing_message_id == msg.get("id") and msg["role"] == "user":
                edited_content = st.text_area(
                    "Edit your message:",
                    value=msg["content"],
                    key=f"edit_area_{msg['id']}"
                )
                col1, col2 = st.columns([1, 1])
                with col1:
                    if st.button("Save", key=f"save_edit_{msg['id']}"):
                        edit_message(msg["id"], edited_content)
                        st.session_state.editing_message_id = None
                        st.rerun()
                with col2:
                    if st.button("Cancel", key=f"cancel_edit_{msg['id']}"):
                        st.session_state.editing_message_id = None
                        st.rerun()
            else:
                st.markdown(msg["content"])
                
                if msg["role"] == "user":
                    if msg.get("is_edited"):
                        st.caption("✏️ Edited")
                    if st.button("✏️ Edit", key=f"edit_btn_{idx}"):
                        st.session_state.editing_message_id = msg.get("id")
                        st.rerun()
                    # Show optimized prompt near the question (from next assistant message)
                    if idx + 1 < len(st.session_state.messages):
                        next_msg = st.session_state.messages[idx + 1]
                        if next_msg.get("role") == "assistant":
                            meta = next_msg.get("metadata", {}) or {}
                            optimized = meta.get("optimized_question")
                            if optimized:
                                st.markdown("**Prompt Optimization**")
                                st.write(f"Given: {msg.get('content','')}")
                                st.write(f"Optimized: {optimized}")
                
                if msg["role"] == "assistant":
                    metadata = msg.get("metadata", {})
                    if metadata.get("conf"):
                        st.markdown(f"**Confidence:** {metadata['conf']}")
                    if metadata.get("caveat"):
                        st.info(f"**Note:** {metadata['caveat']}")
                    
                    if st.session_state.show_evidence and msg.get("evidence"):
                        with st.expander("📚 Evidence Used"):
                            for i, chunk in enumerate(msg["evidence"], 1):
                                st.markdown(f"**Chunk {i}**")
                                st.write(chunk)
                                st.markdown("---")
                    
                    # Prompt optimization display moved to user message above
                    
                    followups = metadata.get("followups", [])
                    if followups:
                        st.markdown("**Suggested follow-ups:**")
                        for fq in followups:
                            if st.button(fq, key=f"followup_{idx}_{fq[:20]}"):
                                send_message(fq)
                                st.rerun()
                    
                    # Add Quiz Button for the last assistant message
                    if idx == len(st.session_state.messages) - 1:
                        if st.button("📝 Take a Quiz on this topic", key=f"quiz_btn_{idx}"):
                            generate_quiz()
                            st.rerun()

    # ============ Quiz Section ============
    if st.session_state.current_quiz:
        st.divider()
        st.subheader("📝 Knowledge Check")
        
        if st.session_state.quiz_submitted:
            score_data = st.session_state.quiz_score
            if score_data:
                pct = score_data.get('percentage', 0.0)
                marks_100 = int(round(pct))
                uname = (st.session_state.user or {}).get("username", "Student")
                st.success(f"Quiz Completed for {uname}! Score: {score_data.get('score')} ({pct:.1f}%) • Marks: {marks_100}/100")
                
                # Detailed report: correct answers, user's answers, explanations
                st.markdown("**Detailed Report**")
                items = st.session_state.quiz_user_answers or []
                for i, item in enumerate(items, start=1):
                    is_correct = item.get("is_correct", False)
                    color = "green" if is_correct else "red"
                    st.markdown(f"**{i}. {item.get('question','')}**")
                    st.write(f"Difficulty: {item.get('difficulty','N/A')}")
                    st.markdown(f"<span style='color:{color}'>Your Answer: {item.get('selected_answer','')}</span>", unsafe_allow_html=True)
                    st.write(f"Correct Answer: {item.get('correct_answer','')}")
                    if item.get("explanation"):
                        st.caption(f"Explanation: {item.get('explanation')}")
                    st.markdown("---")
                
                # Download PDF
                if st.button("📄 Generate Quiz Report (PDF)"):
                    with st.spinner("Preparing PDF report..."):
                        pdf_bytes = export_quiz_report(
                            concept=score_data.get("concept", "General"),
                            percentage=pct,
                            quiz_items=items,
                            student_name=uname
                        )
                        st.session_state.quiz_pdf_data = pdf_bytes
                        st.session_state.show_quiz_pdf_download = True
                        st.success("Report generated")
                
                if st.session_state.show_quiz_pdf_download and st.session_state.quiz_pdf_data:
                    fname = f"EduReflect_Quiz_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    st.download_button(
                        label="⬇️ Download Quiz Report",
                        data=st.session_state.quiz_pdf_data,
                        file_name=fname,
                        mime="application/pdf"
                    )
                
                if st.button("Close Quiz"):
                    st.session_state.current_quiz = None
                    st.session_state.quiz_submitted = False
                    st.session_state.quiz_score = None
                    st.session_state.quiz_user_answers = None
                    st.session_state.quiz_pdf_data = None
                    st.session_state.show_quiz_pdf_download = False
                    st.rerun()
        else:
            with st.form("quiz_form"):
                answers = []
                for i, q in enumerate(st.session_state.current_quiz):
                    st.markdown(f"**{i+1}. {q['question']}**")
                    options = q.get("options", [])
                    selected = st.radio(f"Select answer for Q{i+1}:", options, key=f"q_{i}", index=None)
                    answers.append({"question": q, "selected": selected})
                    st.markdown("---")
                
                if st.form_submit_button("Submit Answers"):
                    # Grade locally first to send correct/incorrect to backend
                    graded_results = []
                    detailed_items = []
                    all_answered = True
                    for ans in answers:
                        if not ans["selected"]:
                            all_answered = False
                            break
                        
                        q = ans["question"]
                        resolved_correct, resolved_index = _map_correct_answer(q)
                        is_correct = _normalize_text(ans["selected"]) == _normalize_text(resolved_correct) or (
                            _normalize_text(q.get("correct_answer","")) in _normalize_text(ans["selected"]) or
                            _normalize_text(ans["selected"]) in _normalize_text(q.get("correct_answer",""))
                        )
                        graded_results.append({
                            "question": q["question"],
                            "is_correct": is_correct
                        })
                        detailed_items.append({
                            "question": q.get("question"),
                            "selected_answer": ans["selected"],
                            "correct_answer": resolved_correct,
                            "explanation": q.get("explanation", ""),
                            "difficulty": q.get("difficulty", ""),
                            "is_correct": is_correct
                        })
                    
                    if not all_answered:
                        st.error("Please answer all questions.")
                    else:
                        st.session_state.quiz_user_answers = detailed_items
                        submit_quiz_answers(graded_results)
                        st.rerun()
            
            if st.button("Cancel Quiz"):
                st.session_state.current_quiz = None
                st.rerun()

    # ============ ChatGPT-Style Input Area ============
    col1, col2 = st.columns([6, 1])
    
    with col1:
        # Use a key that changes when we want to clear
        input_key = "chat_input_main" if not st.session_state.get("clear_input", False) else "chat_input_clear"
        if st.session_state.get("clear_input", False):
            st.session_state.clear_input = False
        
        prompt = st.text_input(
            "Ask a question...",
            key=input_key,
            label_visibility="collapsed"
        )
    
    with col2:
        # File upload button (ChatGPT style)
        uploaded_file = st.file_uploader(
            "📎 Upload document",
            type=["pdf", "docx"],
            key="file_upload",
            label_visibility="collapsed"
        )
        
        # Send button
        send_button = st.empty()
        with send_button.container():
            send_clicked = st.button("Send", use_container_width=True, disabled=not prompt.strip())
    
    # Handle send button click
    if send_clicked and prompt.strip():
        # Process uploaded file if any
        if uploaded_file and not any(d['filename'] == uploaded_file.name for d in st.session_state.uploaded_documents):
            with st.spinner(f"Processing {uploaded_file.name}..."):
                doc_result = process_uploaded_file(uploaded_file)
                if doc_result:
                    st.session_state.uploaded_documents.append(doc_result)
                    st.success(f"{uploaded_file.name} processed")
        
        # Send message
        document_context = ""
        if st.session_state.uploaded_documents:
            document_context = "\n\n".join([doc['full_text'] or doc['content'] for doc in st.session_state.uploaded_documents])
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = send_message(prompt, document_context)
                if result:
                    st.markdown(result["assistant_message"]["content"])
                else:
                    st.error("Failed to get response.")
        
        # Clear input by triggering a rerun with different key
        st.session_state.clear_input = True
        st.rerun()

st.divider()
st.caption("EduReflect • Educational RAG System")
