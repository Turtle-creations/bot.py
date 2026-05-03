import sqlite3
from contextlib import contextmanager

from config import DATABASE_PATH, DATA_DIR


class Database:
    def __init__(self, path):
        self.path = str(path)

    def initialize(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        with self.connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    is_premium INTEGER NOT NULL DEFAULT 0,
                    premium_expires_at TEXT,
                    daily_question_date TEXT,
                    daily_question_count INTEGER NOT NULL DEFAULT 0,
                    pdf_generation_count INTEGER NOT NULL DEFAULT 0,
                    quiz_played INTEGER NOT NULL DEFAULT 0,
                    correct_answers INTEGER NOT NULL DEFAULT 0,
                    wrong_answers INTEGER NOT NULL DEFAULT 0,
                    score REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exams (
                    exam_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE,
                    description TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS exam_sets (
                    set_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    is_premium_locked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE (exam_id, title),
                    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS questions (
                    question_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exam_id INTEGER NOT NULL,
                    set_id INTEGER NOT NULL,
                    question_text TEXT NOT NULL,
                    option_a TEXT NOT NULL,
                    option_b TEXT NOT NULL,
                    option_c TEXT NOT NULL,
                    option_d TEXT NOT NULL,
                    correct_option TEXT NOT NULL,
                    explanation TEXT,
                    image_path TEXT,
                    time_limit INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (exam_id) REFERENCES exams(exam_id) ON DELETE CASCADE,
                    FOREIGN KEY (set_id) REFERENCES exam_sets(set_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    day_of_week INTEGER,
                    send_time TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    last_sent_at TEXT
                );

                CREATE TABLE IF NOT EXISTS payment_orders (
                    order_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    plan_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payment_url TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS payments (
                    payment_id TEXT PRIMARY KEY,
                    order_id TEXT,
                    user_id INTEGER NOT NULL,
                    plan_type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    expiry_date TEXT NOT NULL,
                    raw_payload TEXT
                );

                CREATE TABLE IF NOT EXISTS processed_webhooks (
                    event_id TEXT PRIMARY KEY,
                    payment_id TEXT,
                    order_id TEXT,
                    received_at TEXT NOT NULL,
                    last_seen_at TEXT,
                    duplicate_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS quiz_attempts (
                    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    set_id INTEGER NOT NULL,
                    requested_count INTEGER NOT NULL,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    wrong_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0,
                    ended_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS support_messages (
                    support_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    admin_reply TEXT,
                    replied_at TEXT,
                    admin_chat_id INTEGER,
                    admin_message_id INTEGER
                );
                """
            )
            self._ensure_column(conn, "users", "is_premium", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "premium_expires_at", "TEXT")
            self._ensure_column(conn, "users", "daily_question_date", "TEXT")
            self._ensure_column(conn, "users", "daily_question_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "pdf_generation_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "quiz_played", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "correct_answers", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "wrong_answers", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "score", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "users", "updated_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "exam_sets", "is_premium_locked", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "support_messages", "admin_chat_id", "INTEGER")
            self._ensure_column(conn, "support_messages", "admin_message_id", "INTEGER")
            self._ensure_column(conn, "processed_webhooks", "payment_id", "TEXT")
            self._ensure_column(conn, "processed_webhooks", "order_id", "TEXT")
            self._ensure_column(conn, "processed_webhooks", "last_seen_at", "TEXT")
            self._ensure_column(conn, "processed_webhooks", "duplicate_count", "INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA temp_store=MEMORY")

        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_column(self, conn, table_name: str, column_name: str, definition: str):
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


database = Database(DATABASE_PATH)
