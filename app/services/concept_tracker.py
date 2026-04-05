from sqlalchemy.orm import Session
from app.database.models import UserConceptProgress
from datetime import datetime

def update_user_progress(user_id: str, concept: str, is_correct: bool, db: Session):
    """
    Update user's progress for a specific concept.
    """
    progress = db.query(UserConceptProgress).filter(
        UserConceptProgress.user_id == user_id,
        UserConceptProgress.concept == concept
    ).first()
    
    if not progress:
        progress = UserConceptProgress(
            user_id=user_id,
            concept=concept,
            mastery_level=1,
            questions_answered=0,
            correct_answers=0
        )
        db.add(progress)
    
    progress.questions_answered += 1
    if is_correct:
        progress.correct_answers += 1
        # Simple mastery logic: +1 for every 3 correct answers, max 10
        if progress.correct_answers % 3 == 0 and progress.mastery_level < 10:
            progress.mastery_level += 1
    
    progress.last_practiced = datetime.utcnow()
    db.commit()
    db.refresh(progress)
    return progress

def get_user_mastery(user_id: str, db: Session):
    """
    Get all mastery records for a user.
    """
    return db.query(UserConceptProgress).filter(UserConceptProgress.user_id == user_id).all()
