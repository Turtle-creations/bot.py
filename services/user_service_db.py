from datetime import date, datetime, timezone

from config import ADMINS, SUPREME_ADMIN_ID
from db.database import database
from utils.logging_utils import get_logger


logger = get_logger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_utc_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


class UserService:
    def admin_storage_ready(self) -> bool:
        return database.table_exists("users")

    def initialize_admin_storage(self):
        logger.info(
            "Admin access configured from config only | supreme_admin_id=%s admins=%s",
            SUPREME_ADMIN_ID,
            sorted(ADMINS),
        )

    def is_supreme_admin(self, user_id: int) -> bool:
        return int(user_id) == int(SUPREME_ADMIN_ID)

    def is_admin(self, user_id: int) -> bool:
        return self.is_supreme_admin(user_id) or int(user_id) in ADMINS

    def ensure_user(self, tg_user) -> dict:
        user_id = tg_user.id
        username = tg_user.username
        full_name = tg_user.full_name

        with database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            timestamp = now_iso()

            if row:
                is_admin = 1 if self.is_admin(user_id) else 0
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, full_name = ?, is_admin = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (username, full_name, is_admin, timestamp, user_id),
                )
            else:
                is_admin = 1 if self.is_admin(user_id) else 0
                conn.execute(
                    """
                    INSERT INTO users (
                        user_id, username, full_name, is_admin, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, username, full_name, is_admin, timestamp, timestamp),
                )

            return self._normalize_premium_status(self.get_user(user_id))

    def get_user(self, user_id: int) -> dict:
        with database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        if row:
            user = dict(row)
        elif self.is_supreme_admin(user_id):
            user = {
                "user_id": user_id,
                "username": None,
                "full_name": "Supreme Admin",
                "is_admin": 1,
                "is_premium": 0,
                "premium_expires_at": None,
                "daily_question_date": None,
                "daily_question_count": 0,
                "pdf_generation_count": 0,
                "quiz_played": 0,
                "correct_answers": 0,
                "wrong_answers": 0,
                "score": 0,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
        else:
            user = {}

        if user and self.is_admin(user_id):
            user["is_admin"] = 1
        return self._normalize_premium_status(user) if user else {}

    def list_users(self) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._normalize_premium_status(dict(row)) for row in rows]

    def get_leaderboard(self, limit: int = 10) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM users
                ORDER BY score DESC, correct_answers DESC, full_name ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._normalize_premium_status(dict(row)) for row in rows]

    def list_admins(self) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE is_admin = 1 ORDER BY full_name ASC"
            ).fetchall()
        admins = [self._normalize_premium_status(dict(row)) for row in rows]
        if not any(item["user_id"] == SUPREME_ADMIN_ID for item in admins):
            admins.insert(0, self.get_user(SUPREME_ADMIN_ID))
        return admins

    def list_non_admins(self) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE is_admin = 0 ORDER BY full_name ASC"
            ).fetchall()
        return [self._normalize_premium_status(dict(row)) for row in rows]

    def get_admin_debug_info(self, user_id: int) -> dict:
        with database.connection() as conn:
            row = conn.execute(
                "SELECT user_id, is_admin FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        exists = bool(row)
        is_admin_column = int(row["is_admin"]) if row and row["is_admin"] is not None else None
        is_supreme = self.is_supreme_admin(user_id)
        final_access_allowed = is_supreme or is_admin_column == 1

        return {
            "user_id": user_id,
            "exists": exists,
            "is_admin_column": is_admin_column,
            "is_supreme_admin": is_supreme,
            "final_access_allowed": final_access_allowed,
        }

    def set_admin_status(self, user_id: int, is_admin: bool):
        if self.is_supreme_admin(user_id):
            return self.get_user(user_id)

        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET is_admin = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if is_admin else 0, now_iso(), user_id),
            )
        return self.get_user(user_id)

    def promote_to_admin(self, user_id: int) -> tuple[dict | None, str]:
        if not self.admin_storage_ready():
            raise RuntimeError("Admins table was not found.")

        if self.is_supreme_admin(user_id):
            return self.get_user(user_id), "supreme_admin"

        existing = self.get_user(user_id)
        if existing and existing.get("is_admin"):
            logger.info("Promote admin skipped | target_user_id=%s reason=already_admin", user_id)
            return existing, "already_admin"

        action = "updated" if existing else "inserted"
        with database.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    user_id,
                    username,
                    full_name,
                    is_admin,
                    created_at,
                    updated_at
                )
                VALUES (?, NULL, ?, 1, datetime('now'), datetime('now'))
                ON CONFLICT(user_id) DO UPDATE SET
                    is_admin = 1,
                    updated_at = datetime('now')
                """,
                (
                    user_id,
                    f"Admin {user_id}",
                ),
            )

        if action == "inserted":
            logger.info(
                "Promote admin success | target_user_id=%s row_inserted=1 placeholder_created=1",
                user_id,
            )
        else:
            logger.info("Promote admin success | target_user_id=%s row_updated=1", user_id)

        return self.get_user(user_id), action

    def demote_admin(self, user_id: int) -> dict | None:
        if self.is_supreme_admin(user_id):
            return None

        user = self.get_user(user_id)
        if not user or not user.get("is_admin"):
            return None

        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET is_admin = 0, updated_at = ?
                WHERE user_id = ?
                """,
                (now_iso(), user_id),
            )
        return self.get_user(user_id)

    def record_quiz_start(self, user_id: int):
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET quiz_played = quiz_played + 1,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now_iso(), user_id),
            )

    def record_answer(self, user_id: int, correct: bool):
        with database.connection() as conn:
            if correct:
                conn.execute(
                    """
                    UPDATE users
                    SET correct_answers = correct_answers + 1,
                        score = score + 1,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now_iso(), user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE users
                    SET wrong_answers = wrong_answers + 1,
                        score = score - 0.25,
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (now_iso(), user_id),
                )

    def record_quiz_attempt(
        self,
        user_id: int,
        set_id: int,
        requested_count: int,
        correct_count: int,
        wrong_count: int,
        skipped_count: int,
        ended_reason: str,
    ):
        with database.connection() as conn:
            conn.execute(
                """
                INSERT INTO quiz_attempts (
                    user_id, set_id, requested_count, correct_count, wrong_count,
                    skipped_count, ended_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    set_id,
                    requested_count,
                    correct_count,
                    wrong_count,
                    skipped_count,
                    ended_reason,
                    now_iso(),
                ),
            )

    def sync_json_user_stats(self, users: list[dict]):
        timestamp = now_iso()

        with database.connection() as conn:
            for user in users:
                if not isinstance(user, dict) or "id" not in user:
                    continue

                conn.execute(
                    """
                    INSERT INTO users (
                        user_id, username, full_name, is_admin, is_premium,
                        premium_expires_at, daily_question_date, daily_question_count, pdf_generation_count,
                        quiz_played, correct_answers, wrong_answers, score, created_at, updated_at
                    ) VALUES (?, NULL, ?, ?, 0, NULL, NULL, 0, 0, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        full_name = excluded.full_name,
                        quiz_played = excluded.quiz_played,
                        correct_answers = excluded.correct_answers,
                        wrong_answers = excluded.wrong_answers,
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user["id"],
                        user.get("name", "Unknown"),
                        1 if self.is_supreme_admin(user["id"]) else 0,
                        user.get("quiz_played", 0),
                        user.get("correct", 0),
                        user.get("wrong", 0),
                        user.get("score", 0),
                        timestamp,
                        timestamp,
                    ),
                )

    def can_generate_free_pdf(self, user: dict) -> bool:
        return int(user.get("pdf_generation_count", 0)) < 1

    def record_pdf_generation(self, user_id: int):
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET pdf_generation_count = pdf_generation_count + 1,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now_iso(), user_id),
            )

    def set_premium_expiry(self, user_id: int, expiry_iso: str | None, is_premium: bool):
        normalized_expiry = expiry_iso
        if expiry_iso:
            parsed_expiry = parse_utc_datetime(expiry_iso)
            normalized_expiry = parsed_expiry.replace(microsecond=0).isoformat() if parsed_expiry else expiry_iso
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET is_premium = ?, premium_expires_at = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (1 if is_premium else 0, normalized_expiry, now_iso(), user_id),
            )
        return self.get_user(user_id)

    def _normalize_premium_status(self, user: dict) -> dict:
        if not user:
            return {}

        user_id = user.get("user_id")
        if user_id is None:
            logger.warning(
                "Premium normalization skipped | reason=user_id_missing user=%s",
                user,
            )
            return user

        expiry = user.get("premium_expires_at")
        if not expiry:
            return user

        expiry_dt = parse_utc_datetime(expiry)
        if not expiry_dt:
            logger.warning(
                "Premium normalization skipped | user_id=%s reason=invalid_expiry_format premium_expires_at=%s",
                user_id,
                expiry,
            )
            return user

        if expiry_dt > datetime.now(timezone.utc):
            return user

        if user.get("is_premium"):
            try:
                with database.connection() as conn:
                    conn.execute(
                        """
                        UPDATE users
                        SET is_premium = 0, updated_at = ?
                        WHERE user_id = ?
                        """,
                        (now_iso(), user_id),
                    )
                user["is_premium"] = 0
                logger.info(
                    "Premium normalized | user_id=%s action=expired_premium_downgraded expiry=%s",
                    user_id,
                    expiry,
                )
            except Exception:
                logger.exception(
                    "Premium normalization failed | user_id=%s sql=expired_premium_update expiry=%s",
                    user_id,
                    expiry,
                )

        return user

    def reset_daily_counter_if_needed(self, user: dict) -> dict:
        today = date.today().isoformat()

        if user.get("daily_question_date") == today:
            return user

        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET daily_question_date = ?, daily_question_count = 0, updated_at = ?
                WHERE user_id = ?
                """,
                (today, now_iso(), user["user_id"]),
            )

        return self.get_user(user["user_id"])

    def increment_daily_questions(self, user_id: int, count: int):
        user = self.reset_daily_counter_if_needed(self.get_user(user_id))
        today = date.today().isoformat()

        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET daily_question_date = ?,
                    daily_question_count = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (
                    today,
                    user["daily_question_count"] + count,
                    now_iso(),
                    user_id,
                ),
            )


user_service = UserService()
