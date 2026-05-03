# -*- coding: utf-8 -*-

import re

from config import ADMINS, SUPREME_ADMIN_ID
from db.database import database
from services.user_service_db import now_iso
from utils.logging_utils import get_logger


logger = get_logger(__name__)


class SupportService:
    TICKET_ID_PATTERN = re.compile(r"Ticket ID:</b>\s*(\d+)", re.IGNORECASE)

    def get_support_admin_ids(self) -> list[int]:
        admin_ids = {int(admin_id) for admin_id in ADMINS if admin_id}
        if SUPREME_ADMIN_ID:
            admin_ids.add(int(SUPREME_ADMIN_ID))
        return sorted(admin_ids)

    def get_support_admin_id(self) -> int | None:
        admin_ids = self.get_support_admin_ids()
        return admin_ids[0] if admin_ids else None

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

    def get_ticket_by_id(self, support_id: int) -> dict | None:
        with database.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM support_messages
                WHERE support_id = ?
                LIMIT 1
                """,
                (support_id,),
            ).fetchone()
        return dict(row) if row else None

    def extract_ticket_id_from_text(self, text: str | None) -> int | None:
        if not text:
            return None
        match = self.TICKET_ID_PATTERN.search(text)
        if not match:
            return None
        return int(match.group(1))

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
