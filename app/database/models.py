from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, Text, ForeignKey, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from passlib.context import CryptContext
from jose import JWTError, jwt
import logging
import secrets
import uuid

from app.utils.config import SECRET_KEY as CONFIGURED_SECRET_KEY

Base = declarative_base()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
if CONFIGURED_SECRET_KEY:
    SECRET_KEY = CONFIGURED_SECRET_KEY
else:
    # Never fall back to a known value: an ephemeral key is safe, it just logs everyone out on restart.
    SECRET_KEY = secrets.token_hex(32)
    logging.getLogger(__name__).warning("SECRET_KEY is not set; using a random key for this process.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    preferred_language = Column(String, default="en")
    
    # Subscription fields
    subscription_tier = Column(String, default="free")  # free, basic, premium
    subscription_active = Column(Boolean, default=True)
    subscription_expires_at = Column(DateTime, nullable=True)
    monthly_chat_limit = Column(Integer, default=50)  # Free tier limit
    monthly_chats_used = Column(Integer, default=0)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    
    def verify_password(self, plain_password: str) -> bool:
        return pwd_context.verify(plain_password, self.hashed_password)
    
    def get_subscription_status(self) -> dict:
        """Get user's subscription status"""
        now = datetime.utcnow()
        is_expired = self.subscription_expires_at and now > self.subscription_expires_at
        
        return {
            "tier": self.subscription_tier,
            "active": self.subscription_active and not is_expired,
            "expires_at": self.subscription_expires_at.isoformat() if self.subscription_expires_at else None,
            "monthly_limit": self.monthly_chat_limit,
            "monthly_used": self.monthly_chats_used,
            "remaining_chats": max(0, self.monthly_chat_limit - self.monthly_chats_used)
        }


class Project(Base):
    """Projects group multiple chats around a topic (like ChatGPT projects)"""
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="projects")
    chats = relationship("Chat", back_populates="project", cascade="all, delete-orphan")


class Chat(Base):
    """Individual chat conversations"""
    __tablename__ = "chats"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    project_id = Column(String, ForeignKey("projects.id"), nullable=True)
    title = Column(String, default="New Chat")
    summary = Column(Text, nullable=True)
    is_temporary = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    pin_order = Column(Integer, nullable=True)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="chats")
    project = relationship("Project", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    """Individual messages within a chat"""
    __tablename__ = "messages"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    original_content = Column(Text, nullable=True)
    is_edited = Column(Boolean, default=False)
    evidence = Column(JSON, nullable=True)
    msg_metadata = Column(JSON, nullable=True)
    version = Column(Integer, default=1)
    parent_message_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime, nullable=True)
    
    chat = relationship("Chat", back_populates="messages")


class MessageEditHistory(Base):
    """Track edit history for messages"""
    __tablename__ = "message_edits"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    previous_content = Column(Text, nullable=False)
    new_content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False)
    edited_at = Column(DateTime, default=datetime.utcnow)


class UserConceptProgress(Base):
    """User learning progress tracking"""
    __tablename__ = "user_concept_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    concept = Column(String, nullable=False)
    mastery_level = Column(Integer, default=1)
    questions_answered = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    last_practiced = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class StudySession(Base):
    """Study sessions tracking"""
    __tablename__ = "study_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    session_id = Column(String, unique=True, nullable=False)
    subject = Column(String, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    planned_duration = Column(Integer, nullable=True)  # in minutes
    actual_duration = Column(Float, nullable=True)  # in minutes
    focus_score = Column(Float, nullable=True)
    questions_asked = Column(Integer, default=0)
    concepts_covered = Column(JSON, nullable=True)  # JSON array
    productivity_score = Column(Float, nullable=True)
    session_insights = Column(JSON, nullable=True)  # JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class GeneratedQuestion(Base):
    """Generated questions storage"""
    __tablename__ = "generated_questions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    concept = Column(String, nullable=False)
    question_type = Column(String, nullable=False)
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=True)
    options = Column(JSON, nullable=True)  # JSON array for multiple choice
    explanation = Column(Text, nullable=True)
    difficulty = Column(String, default='medium')
    times_asked = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class QuestionAttempt(Base):
    """Question attempts tracking"""
    __tablename__ = "question_attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("generated_questions.id"), nullable=False)
    user_answer = Column(Text, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class WeeklyQuiz(Base):
    """Weekly quiz collections"""
    __tablename__ = "weekly_quizzes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    questions = Column(JSON, nullable=False)  # Array of question objects
    week_start_date = Column(DateTime, nullable=False)  # Monday of the week
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)  # Optional expiration
    
    user = relationship("User", backref="weekly_quizzes")
    attempts = relationship("WeeklyQuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class WeeklyQuizAttempt(Base):
    """Weekly quiz attempt tracking"""
    __tablename__ = "weekly_quiz_attempts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(String, ForeignKey("weekly_quizzes.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    answers = Column(JSON, nullable=True)  # User's answers
    score = Column(Float, nullable=True)  # Percentage score
    total_questions = Column(Integer, nullable=False)
    correct_answers = Column(Integer, nullable=False)
    time_taken_seconds = Column(Integer, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    
    quiz = relationship("WeeklyQuiz", back_populates="attempts")
    user = relationship("User", backref="weekly_quiz_attempts")


# JWT token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """Verify JWT token and return user ID"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None


def get_password_hash(password: str) -> str:
    """Hash password with bcrypt"""
    # With bcrypt 4.3.0, we don't need manual truncation
    return pwd_context.hash(password)


# Database setup
DATABASE_URL = "sqlite:///./edureflect.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()