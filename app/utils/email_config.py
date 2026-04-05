import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")  # Your email address
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # App password (not regular password)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")    # Same as SMTP_USERNAME usually
SENDER_NAME = os.getenv("SENDER_NAME", "EduReflect")