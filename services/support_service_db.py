# -*- coding: utf-8 -*-

from config import ADMINS, SUPREME_ADMIN_ID
from db.database import database
from services.user_service_db import now_iso
from utils.logging_utils import get_logger


logger = get_logger(__name__)


class SupportService:
    def get_support_admin_id(self) -> int | None:
        if SUPREME_ADMIN_ID in ADMINS:
            return SUPREME_ADMIN_ID
        return next(iter(ADMINS), None)

    def create_ticket(self, user: dict, message_text: str) -> int:
        with database.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO support_messages (
                    user_id, username, full_name, message, created_at, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user["user_id"],
                    user.get("username"),
                    user.get("full_name") or "Unknown",
                    message_text,
                    now_iso(),
                    "open",
                ),
            )
            support_id = cursor.lastrowid

        logger.info("Support ticket created | support_id=%s user_id=%s", support_id, user["user_id"])
        return int(support_id)

    def attach_admin_message(self, support_id: int, admin_chat_id: int, admin_message_id: int):
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE support_messages
                SET admin_chat_id = ?, admin_message_id = ?
                WHERE support_id = ?
                """,
                (admin_chat_id, admin_message_id, support_id),
            )

    def get_ticket_by_admin_message(self, admin_chat_id: int, admin_message_id: int) -> dict | None:
        with database.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM support_messages
                WHERE admin_chat_id = ? AND admin_message_id = ?
                ORDER BY support_id DESC
                LIMIT 1
                """,
                (admin_chat_id, admin_message_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_replied(self, support_id: int, reply_text: str):
        with database.connection() as conn:
            conn.execute(
                """
                UPDATE support_messages
                SET status = ?, admin_reply = ?, replied_at = ?
                WHERE support_id = ?
                """,
                ("replied", reply_text, now_iso(), support_id),
            )
        logger.info("Support ticket replied | support_id=%s", support_id)


support_service = SupportService()
