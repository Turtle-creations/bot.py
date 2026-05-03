import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGE_DIR = DATA_DIR / "images"
DATABASE_PATH = DATA_DIR / "quiz_bot_v2.db"


def _read_admin_ids(raw_value: str) -> list[int]:
    items = []

    for value in raw_value.split(","):
        value = value.strip()
        if value.isdigit():
            items.append(int(value))

    return items


def _read_bool_env(name: str, default: bool = False) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
SUPREME_ADMIN_ID = int(os.getenv("SUPREME_ADMIN_ID", "1341448466"))
ADMINS = {
    *(_read_admin_ids(os.getenv("ADMINS", "8794853346,1819574740,820743761"))),
}
FREE_DAILY_QUESTION_LIMIT = int(os.getenv("FREE_DAILY_QUESTION_LIMIT", "10"))
DEFAULT_QUESTION_TIME = int(os.getenv("DEFAULT_QUESTION_TIME", "15"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
PAYMENT_DEBUG = _read_bool_env("PAYMENT_DEBUG", False)
