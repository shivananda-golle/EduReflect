import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
import logging

from app.utils.email_config import (
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_PASSWORD,
    SENDER_EMAIL,
    SENDER_NAME
)

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    plain_content: Optional[str] = None
) -> bool:
    """
    Send an email to a single recipient.
    
    Args:
        to_email: Recipient's email address
        subject: Email subject line
        html_content: HTML body of the email
        plain_content: Plain text fallback (optional)
    
    Returns:
        True if email sent successfully, False otherwise
    """
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.error("Email credentials not configured")
        return False
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        message["To"] = to_email
        
        # Add plain text version (fallback)
        if plain_content:
            part1 = MIMEText(plain_content, "plain")
            message.attach(part1)
        
        # Add HTML version
        part2 = MIMEText(html_content, "html")
        message.attach(part2)
        
        # Connect and send
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()  # Enable security
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, message.as_string())
        
        logger.info(f"Email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def format_quiz_link_email(
    username: str,
    quiz_title: str,
    quiz_link: str,
    expiry_date: Optional[str] = None
) -> tuple:
    """
    Format quiz link email.
    
    Args:
        username: Student's username or name
        quiz_title: Title of the quiz
        quiz_link: URL to access the quiz
        expiry_date: Optional expiry date string
    
    Returns:
        Tuple of (html_content, plain_content)
    """
    expiry_text = f" (expires {expiry_date})" if expiry_date else ""
    
    # Build HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4A90D9; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background-color: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px; }}
            .quiz-info {{ background-color: white; padding: 20px; margin: 20px 0; border-radius: 8px; border-left: 4px solid #4A90D9; }}
            .btn {{ display: inline-block; background-color: #4A90D9; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: bold; margin-top: 15px; }}
            .btn:hover {{ background-color: #357ABD; }}
            .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            .expiry {{ color: #e74c3c; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📘 Your Weekly EduReflect Quiz</h1>
            </div>
            <div class="content">
                <p>Hello <strong>{username}</strong>,</p>
                <p>Your personalized weekly quiz is ready! This quiz is designed to test and reinforce your understanding of recent learning topics.</p>
                
                <div class="quiz-info">
                    <h3>{quiz_title}{expiry_text}</h3>
                    <p><strong>What to expect:</strong></p>
                    <ul>
                        <li>5 multiple-choice questions</li>
                        <li>Based on your recent learning activities</li>
                        <li>Timed quiz with instant results</li>
                        <li>Track your progress over time</li>
                    </ul>
                </div>
                
                <p style="text-align: center;">
                    <a href="{quiz_link}" class="btn">Take Your Quiz Now →</a>
                </p>
                
                <p>Completing weekly quizzes helps reinforce your learning and track your educational progress. Make it a habit!</p>
                <p>Happy learning! 📚✨</p>
            </div>
            <div class="footer">
                <p>This is an automated email from EduReflect.</p>
                <p>You're receiving this because you're subscribed to weekly quizzes.</p>
                {"<p class='expiry'>This quiz link expires on " + expiry_date + "</p>" if expiry_date else ""}
            </div>
        </div>
    </body>
    </html>
    """
    
    # Build plain text version
    plain_content = f"""
EduReflect Weekly Quiz

Hello {username},

Your personalized weekly quiz is ready!

{quiz_title}{expiry_text}

What to expect:
- 5 multiple-choice questions
- Based on your recent learning activities  
- Timed quiz with instant results
- Track your progress over time

Take your quiz here: {quiz_link}

Completing weekly quizzes helps reinforce your learning and track your educational progress.

Happy learning!

---
This is an automated email from EduReflect.
{"This quiz link expires on " + expiry_date if expiry_date else ""}
    """
    
    return html_content, plain_content