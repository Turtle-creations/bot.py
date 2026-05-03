from datetime import datetime, timedelta, timezone

from db.database import database
from services.user_service_db import now_iso, parse_utc_datetime, user_service


class PremiumService:
    def is_premium(self, user_id: int) -> bool:
        user = user_service.get_user(user_id)
        return self._is_user_premium(user)

    def _is_user_premium(self, user: dict) -> bool:
        if not user or not user.get("is_premium"):
            return False

        expiry = user.get("premium_expires_at")
        if not expiry:
            return True

        expiry_dt = parse_utc_datetime(expiry)
        if not expiry_dt:
            return False
        return expiry_dt > datetime.now(timezone.utc)

    def status_text(self, user: dict) -> str:
        if not user:
            return "Free"

        if not self._is_user_premium(user):
            expiry = user.get("premium_expires_at")
            if expiry:
                return f"Expired on {expiry.replace('T', ' ')} UTC"
            return "Free"

        expiry = user.get("premium_expires_at")
        return f"Premium until {expiry.replace('T', ' ')} UTC" if expiry else "Premium"

    def remaining_free_questions(self, user: dict, daily_limit: int) -> int:
        user = user_service.reset_daily_counter_if_needed(user)
        if self._is_user_premium(user):
            return 999999
        return max(daily_limit - user.get("daily_question_count", 0), 0)

    def upgrade_user(self, user_id: int, days: int):
        user = user_service.get_user(user_id)
        if not user:
            return None

        current_expiry = user.get("premium_expires_at")
        now = datetime.now(timezone.utc)

        if current_expiry:
            current_dt = parse_utc_datetime(current_expiry)
            if current_dt:
                start = current_dt if current_dt > now else now
            else:
                start = now
        else:
            start = now

        expires_at = (start + timedelta(days=days)).replace(microsecond=0).isoformat()

        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET is_premium = 1,
                    premium_expires_at = ?,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (expires_at, now_iso(), user_id),
            )

        return user_service.get_user(user_id)

    def downgrade_user(self, user_id: int):
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE users
                SET is_premium = 0,
                    premium_expires_at = NULL,
                    updated_at = ?
                WHERE user_id = ?
                """,
                (now_iso(), user_id),
            )

        return user_service.get_user(user_id)

    def list_premium_users(self) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM users
                WHERE is_premium = 1
                ORDER BY premium_expires_at ASC, full_name ASC
                """
            ).fetchall()

        users = [dict(row) for row in rows]
        return [user for user in users if self._is_user_premium(user)]


premium_service = PremiumService()
