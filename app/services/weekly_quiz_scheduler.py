import logging
from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from app.database.models import User, Chat, Message, SessionLocal, WeeklyQuiz
from app.services.question_generator import generate_quiz
from app.services.email_service import send_email, format_quiz_link_email

logger = logging.getLogger(__name__)


def get_week_start_date(date: datetime = None) -> datetime:
    """Get the Monday of the week for a given date"""
    if date is None:
        date = datetime.utcnow()
    # Monday is weekday 0 in Python (Monday=0, Sunday=6)
    days_since_monday = date.weekday()
    week_start = date - timedelta(days=days_since_monday)
    # Set to start of day
    return week_start.replace(hour=0, minute=0, second=0, microsecond=0)


def get_user_recent_content(user_id: str, db: Session, days: int = 7) -> str:
    """
    Get content from user's recent chat messages for quiz generation.
    
    Args:
        user_id: The user's ID
        db: Database session
        days: Number of days to look back (default 7)
    
    Returns:
        Combined text content from recent assistant messages
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    # Get user's recent chats
    recent_chats = db.query(Chat).filter(
        Chat.user_id == user_id,
        Chat.updated_at >= cutoff_date,
        Chat.is_temporary == False
    ).all()
    
    if not recent_chats:
        return ""
    
    # Collect assistant messages (educational content)
    content_parts = []
    for chat in recent_chats:
        assistant_messages = db.query(Message).filter(
            Message.chat_id == chat.id,
            Message.role == "assistant",
            Message.created_at >= cutoff_date
        ).order_by(Message.created_at.desc()).limit(5).all()
        
        for msg in assistant_messages:
            if msg.content and len(msg.content) > 100:  # Skip very short messages
                content_parts.append(msg.content)
    
    # Combine and limit content
    combined_content = "\n\n".join(content_parts)
    
    # Limit to reasonable size for quiz generation
    return combined_content[:8000] if combined_content else ""


def generate_weekly_quiz_for_user(user_id: str, db: Session) -> Optional[str]:
    """
    Generate a weekly quiz for a user and store it in the database.
    
    Args:
        user_id: The user's ID
        db: Database session
    
    Returns:
        Quiz ID if successful, None if failed
    """
    # Get recent content (use all available content, even if minimal)
    content = get_user_recent_content(user_id, db)
    
    # If no content, use a generic educational fallback
    if not content or len(content) < 50:
        content = """
        General knowledge topics in science and mathematics including:
        - Physics: Newton's laws, gravity, energy conservation
        - Chemistry: Periodic table, chemical reactions, acids and bases  
        - Biology: Cell structure, photosynthesis, human anatomy
        - Mathematics: Algebra, geometry, statistics, calculus basics
        - History: Scientific discoveries, important inventions
        - General knowledge: Current events, geography, literature
        """
        logger.info(f"Using fallback content for user {user_id} due to insufficient chat history")
    
    # Generate quiz using existing function
    try:
        quiz_questions = generate_quiz(content, num_questions=5)
        if not quiz_questions:
            logger.error(f"Failed to generate quiz questions for user {user_id}")
            return None
            
    except Exception as e:
        logger.error(f"Failed to generate quiz for user {user_id}: {e}")
        return None
    
    # Get the week start date (Monday of current week)
    week_start = get_week_start_date()
    
    # Check if user already has a quiz for this week
    existing_quiz = db.query(WeeklyQuiz).filter(
        WeeklyQuiz.user_id == user_id,
        WeeklyQuiz.week_start_date == week_start
    ).first()
    
    if existing_quiz:
        logger.info(f"User {user_id} already has a quiz for this week")
        return existing_quiz.id
    
    # Create new weekly quiz
    try:
        new_quiz = WeeklyQuiz(
            user_id=user_id,
            title=f"Your Weekly EduReflect Quiz - {week_start.strftime('%B %d, %Y')}",
            description="Test your understanding of recent learning topics",
            questions=quiz_questions,
            week_start_date=week_start,
            expires_at=week_start + timedelta(days=7)  # Expires next Monday
        )
        
        db.add(new_quiz)
        db.commit()
        db.refresh(new_quiz)
        
        logger.info(f"Created weekly quiz {new_quiz.id} for user {user_id}")
        return new_quiz.id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save weekly quiz for user {user_id}: {e}")
        return None


def send_weekly_quiz_email(user: User, quiz_id: str, db: Session) -> bool:
    """
    Send weekly quiz email with link to a user.
    
    Args:
        user: User object
        quiz_id: ID of the weekly quiz
        db: Database session
    
    Returns:
        True if email sent successfully
    """
    if not user.email:
        logger.warning(f"User {user.id} has no email address")
        return False
    
    # Get quiz details
    quiz = db.query(WeeklyQuiz).filter(WeeklyQuiz.id == quiz_id).first()
    if not quiz:
        logger.error(f"Quiz {quiz_id} not found")
        return False
    
    # Create quiz link (assuming frontend URL structure)
    base_url = "http://localhost:8501"  # Update this for production
    quiz_link = f"{base_url}/?quiz={quiz_id}"
    
    # Format expiry date
    expiry_str = quiz.expires_at.strftime("%B %d, %Y") if quiz.expires_at else None
    
    # Format the email
    display_name = user.full_name or user.username
    html_content, plain_content = format_quiz_link_email(
        display_name, 
        quiz.title, 
        quiz_link, 
        expiry_str
    )
    
    # Send the email
    subject = "📘 Your Weekly EduReflect Quiz is Ready!"
    return send_email(user.email, subject, html_content, plain_content)


def process_weekly_quizzes():
    """
    Main function to process and send weekly quizzes to all active users.
    This should be called by a scheduler (cron job, APScheduler, etc.)
    """
    logger.info("Starting weekly quiz processing...")
    
    db = SessionLocal()
    try:
        # Get all active users
        active_users = db.query(User).filter(
            User.is_active == True
        ).all()
        
        sent_count = 0
        failed_count = 0
        skipped_count = 0
        
        for user in active_users:
            try:
                # Generate/store weekly quiz (always creates one)
                quiz_id = generate_weekly_quiz_for_user(user.id, db)
                
                if not quiz_id:
                    logger.error(f"Failed to generate/store quiz for user {user.username}")
                    failed_count += 1
                    continue
                
                # Send email with quiz link
                success = send_weekly_quiz_email(user, quiz_id, db)
                
                if success:
                    sent_count += 1
                    logger.info(f"Sent weekly quiz email to {user.username}")
                else:
                    failed_count += 1
                    logger.warning(f"Failed to send quiz email to {user.username}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing user {user.id}: {e}")
        
        logger.info(
            f"Weekly quiz processing complete. "
            f"Sent: {sent_count}, Failed: {failed_count}, Skipped: {skipped_count}"
        )
        
        return {
            "sent": sent_count,
            "failed": failed_count,
            "skipped": skipped_count
        }
        
    finally:
        db.close()


def send_quiz_to_single_user(user_id: str) -> dict:
    """
    Send quiz to a single user (useful for testing or manual triggers).
    
    Args:
        user_id: The user's ID
    
    Returns:
        Status dictionary
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            return {"status": "error", "message": "User not found"}
        
        # Generate/store weekly quiz
        quiz_id = generate_weekly_quiz_for_user(user_id, db)
        
        if not quiz_id:
            return {"status": "error", "message": "Failed to generate quiz"}
        
        # Send email
        success = send_weekly_quiz_email(user, quiz_id, db)
        
        if success:
            return {"status": "success", "message": f"Quiz email sent to {user.email}", "quiz_id": quiz_id}
        else:
            return {"status": "error", "message": "Failed to send email"}
            
    finally:
        db.close()