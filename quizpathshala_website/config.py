import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
DATABASE_PATH = DATA_DIR / "quiz_bot_v2.db"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SECRET_KEY = os.getenv("SECRET_KEY", "quizpathshala-web-secret")
PORT = int(os.getenv("PORT", "10000"))
DEFAULT_QUESTION_TIME = int(os.getenv("DEFAULT_QUESTION_TIME", "15"))
FREE_DAILY_QUESTION_LIMIT = int(os.getenv("FREE_DAILY_QUESTION_LIMIT", "10"))

SITE_NAME = "QuizPathshala"
SITE_TAGLINE = "Online quiz preparation platform via Telegram bot"
BOT_URL = os.getenv("BOT_URL", "https://t.me/QuizPathshala_bot")
BOT_USERNAME = os.getenv("BOT_USERNAME", "QuizPathshala_bot")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "")
SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "https://t.me/QuizPathshala_bot")
SUPPORT_HOURS = os.getenv("SUPPORT_HOURS", "Monday to Saturday, 10:00 AM to 7:00 PM IST")
CANONICAL_URL = os.getenv("CANONICAL_URL", "").rstrip("/")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", CANONICAL_URL or "")

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "quizpathshala-admin")
SUPREME_ADMIN_ID = int(os.getenv("SUPREME_ADMIN_ID", "1341448466"))
ADMINS = {
    int(item.strip())
    for item in os.getenv("ADMINS", "").split(",")
    if item.strip().isdigit()
}
