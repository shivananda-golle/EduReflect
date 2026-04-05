"""
Scheduler for running periodic tasks like weekly quiz emails.

You can run this in several ways:
1. As a separate process using APScheduler
2. Using system cron
3. Using a task queue like Celery

This file provides the APScheduler approach.
"""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.weekly_quiz_scheduler import process_weekly_quizzes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_weekly_quiz_job():
    """Wrapper function for the weekly quiz job."""
    logger.info("Running weekly quiz job...")
    try:
        result = process_weekly_quizzes()
        logger.info(f"Weekly quiz job completed: {result}")
    except Exception as e:
        logger.error(f"Weekly quiz job failed: {e}")


def start_scheduler():
    """
    Start the APScheduler to run weekly quiz emails.
    
    Default schedule: Every Sunday at 9:00 AM
    """
    scheduler = BlockingScheduler()
    
    # Schedule weekly quiz emails
    # Runs every Sunday at 9:00 AM
    scheduler.add_job(
        run_weekly_quiz_job,
        trigger=CronTrigger(
            day_of_week='sun',  # Sunday
            hour=9,             # 9 AM
            minute=0
        ),
        id='weekly_quiz_email',
        name='Send weekly quiz emails to all users',
        replace_existing=True
    )
    
    logger.info("Scheduler started. Weekly quizzes will be sent every Sunday at 9:00 AM")
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    start_scheduler()