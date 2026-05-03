# -*- coding: utf-8 -*-

import asyncio
import json
from datetime import datetime, time
from zoneinfo import ZoneInfo

from config import DATA_DIR
from db.database import database
from services.user_service_db import now_iso, user_service
from utils.logging_utils import get_logger


logger = get_logger(__name__)
INDIA_TZ = ZoneInfo("Asia/Kolkata")

DAY_LABELS = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


class NotificationService:
    def __init__(self):
        self.application = None
        self._broadcast_queue = None
        self._broadcast_worker_task = None

    def register_jobs(self, application):
        self.application = application
        self._migrate_legacy_notification()
        self._schedule_from_database()

    async def broadcast(self, message: str):
        if not self.application:
            logger.warning("Broadcast skipped because application is not registered")
            return 0, 0

        users = user_service.list_users()
        total_users = len(users)
        logger.info("Notification broadcast starting | total_users=%s", total_users)
        if not users:
            logger.warning("Notification broadcast skipped because users table is empty")
            return 0, 0

        sent = 0
        failed = 0

        for user in users:
            user_id = user["user_id"]
            try:
                rendered_message = self._render_message_for_user(message, user)
                await self.application.bot.send_message(
                    chat_id=user_id,
                    text=rendered_message,
                )
                sent += 1
                logger.info("Notification send success | user_id=%s", user_id)
            except Exception as exc:
                failed += 1
                logger.exception("Notification send failed | user_id=%s reason=%s", user_id, exc)

        logger.info(
            "Notification broadcast completed | total_users=%s sent=%s failed=%s",
            total_users,
            sent,
            failed,
        )
        return sent, failed

    async def queue_broadcast(self, message: str, *, notification_id: int | None = None, source: str = "manual") -> tuple[bool, str]:
        if not self.application:
            logger.warning("Notification queue skipped because application is not registered")
            return False, "Notification worker is not ready."

        self._ensure_broadcast_worker()
        try:
            self._broadcast_queue.put_nowait(
                {
                    "message": message,
                    "notification_id": notification_id,
                    "source": source,
                }
            )
        except asyncio.QueueFull:
            logger.warning("Notification queue full | source=%s notification_id=%s", source, notification_id)
            return False, "Notification queue is full. Try again shortly."

        queue_size = self._broadcast_queue.qsize()
        logger.info(
            "Notification queued | source=%s notification_id=%s queue_size=%s",
            source,
            notification_id,
            queue_size,
        )
        return True, f"Notification queued. Queue size: {queue_size}."

    async def send_notification_now(self, notification_id: int) -> tuple[bool, str]:
        notification = self.get_schedule(notification_id)
        if not notification:
            logger.warning("Immediate notification send skipped | notification_id=%s missing=1", notification_id)
            return False, "Notification not found."

        logger.info(
            "Immediate notification send requested | notification_id=%s kind=%s send_time=%s day_of_week=%s is_active=%s",
            notification["notification_id"],
            notification["kind"],
            notification["send_time"],
            notification["day_of_week"],
            notification["is_active"],
        )
        return await self.queue_broadcast(
            notification["message"],
            notification_id=notification["notification_id"],
            source="test_send",
        )

    def create_schedule(
        self,
        kind: str,
        message: str,
        send_time: str,
        day_of_week: int | None = None,
        days_of_week: list[int] | None = None,
    ):
        day_value = None
        if kind == "weekly":
            day_list = days_of_week if days_of_week is not None else [day_of_week] if day_of_week is not None else []
            normalized_days = sorted({day for day in day_list if isinstance(day, int) and 0 <= day <= 6})
            day_value = ",".join(str(day) for day in normalized_days)

        with database.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notifications (
                    message, kind, day_of_week, send_time, is_active, created_at
                ) VALUES (?, ?, ?, ?, 1, ?)
                """,
                (message, kind, day_value, send_time, now_iso()),
            )
            notification_id = cursor.lastrowid

        created = self.get_schedule(notification_id)
        if created:
            logger.info(
                "Notification schedule created | notification_id=%s kind=%s send_time=%s day_of_week=%s is_active=%s message=%s",
                created["notification_id"],
                created["kind"],
                created["send_time"],
                created["day_of_week"],
                created["is_active"],
                created["message"],
            )

        self._schedule_single(notification_id, kind, message, send_time, day_value)
        return notification_id

    def list_schedules(self, include_inactive: bool = True) -> list[dict]:
        query = """
            SELECT * FROM notifications
            {where_clause}
            ORDER BY
                CASE kind WHEN 'daily' THEN 0 WHEN 'weekly' THEN 1 ELSE 2 END,
                send_time ASC,
                notification_id DESC
        """
        where_clause = "" if include_inactive else "WHERE is_active = 1"

        with database.connection() as conn:
            rows = conn.execute(query.format(where_clause=where_clause)).fetchall()

        notifications = []
        for row in rows:
            item = dict(row)
            parsed_days = self._parse_days(item.get("day_of_week"))
            item["days_of_week"] = list(parsed_days)
            item["days_text"] = ", ".join(DAY_LABELS[day] for day in parsed_days) if parsed_days else ""
            notifications.append(item)
        return notifications

    def get_schedule(self, notification_id: int) -> dict | None:
        with database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM notifications WHERE notification_id = ?",
                (notification_id,),
            ).fetchone()

        if not row:
            return None

        item = dict(row)
        parsed_days = self._parse_days(item.get("day_of_week"))
        item["days_of_week"] = list(parsed_days)
        item["days_text"] = ", ".join(DAY_LABELS[day] for day in parsed_days) if parsed_days else ""
        return item

    def delete_schedule(self, notification_id: int) -> bool:
        with database.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE notifications
                SET is_active = 0
                WHERE notification_id = ? AND is_active = 1
                """,
                (notification_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            self._remove_scheduled_job(notification_id)
            logger.info("Notification schedule deleted | notification_id=%s", notification_id)
        else:
            logger.warning("Notification schedule delete skipped | notification_id=%s missing_or_inactive=1", notification_id)

        return deleted

    def _schedule_from_database(self):
        with database.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE is_active = 1"
            ).fetchall()

        logger.info("Loaded %s schedules from DB", len(rows))
        server_now = self._server_now()
        india_now = self._india_now()
        logger.info(
            "Notification scheduler runtime | server_time=%s india_time=%s india_timezone=%s",
            server_now.isoformat(),
            india_now.isoformat(),
            INDIA_TZ,
        )

        for row in rows:
            item = dict(row)
            logger.info(
                "Notification schedule loaded | notification_id=%s kind=%s send_time=%s day_of_week=%s message=%s is_active=%s",
                item["notification_id"],
                item["kind"],
                item["send_time"],
                item["day_of_week"],
                item["message"],
                item["is_active"],
            )
            self._schedule_single(
                item["notification_id"],
                item["kind"],
                item["message"],
                item["send_time"],
                item["day_of_week"],
            )

    def _schedule_single(self, notification_id: int, kind: str, message: str, send_time: str, day_of_week):
        if not self.application or not send_time:
            logger.warning(
                "Notification job registration skipped | notification_id=%s application_ready=%s send_time=%s",
                notification_id,
                bool(self.application),
                send_time,
            )
            return

        hour, minute = [int(part) for part in send_time.split(":")]
        schedule_time = time(hour=hour, minute=minute, tzinfo=INDIA_TZ)
        server_now = self._server_now()
        india_now = self._india_now()
        name = self._job_name(notification_id)

        self._remove_scheduled_job(notification_id)

        job_kwargs = {
            "notification_id": notification_id,
            "message": message,
            "kind": kind,
            "send_time": send_time,
            "day_of_week": day_of_week,
        }

        if kind == "daily":
            self.application.job_queue.run_daily(
                self._scheduled_job,
                time=schedule_time,
                name=name,
                data=job_kwargs,
            )
        elif kind == "weekly":
            days = self._parse_days(day_of_week)
            if not days:
                logger.warning(
                    "Notification job registration skipped | notification_id=%s kind=weekly invalid_days=%s",
                    notification_id,
                    day_of_week,
                )
                return
            self.application.job_queue.run_daily(
                self._scheduled_job,
                time=schedule_time,
                days=days,
                name=name,
                data=job_kwargs,
            )
        else:
            logger.warning(
                "Notification job registration skipped | notification_id=%s unsupported_kind=%s",
                notification_id,
                kind,
            )
            return

        next_run = None
        jobs = self.application.job_queue.get_jobs_by_name(name)
        if jobs:
            next_run = getattr(jobs[0], "next_t", None)

        logger.info(
            "Notification job registered | notification_id=%s kind=%s send_time=%s day_of_week=%s server_time=%s india_time=%s scheduled_for=%s Asia/Kolkata next_run=%s",
            notification_id,
            kind,
            send_time,
            day_of_week,
            server_now.isoformat(),
            india_now.isoformat(),
            send_time,
            next_run.isoformat() if hasattr(next_run, "isoformat") else next_run,
        )

    async def _scheduled_job(self, context):
        payload = context.job.data
        server_now = self._server_now()
        india_now = self._india_now()
        logger.info(
            "Scheduled notification job triggered | notification_id=%s kind=%s send_time=%s day_of_week=%s server_time=%s india_time=%s timezone=%s",
            payload["notification_id"],
            payload["kind"],
            payload["send_time"],
            payload["day_of_week"],
            server_now.isoformat(),
            india_now.isoformat(),
            INDIA_TZ,
        )

        queued, result_message = await self.queue_broadcast(
            payload["message"],
            notification_id=payload["notification_id"],
            source="scheduled_job",
        )
        logger.info(
            "Scheduled notification job queued | notification_id=%s queued=%s result=%s",
            payload["notification_id"],
            queued,
            result_message,
        )

    def _migrate_legacy_notification(self):
        legacy_file = DATA_DIR / "notifications.json"
        if not legacy_file.exists():
            return

        with database.connection() as conn:
            count = conn.execute("SELECT COUNT(*) AS count FROM notifications").fetchone()["count"]
            if count:
                return

        try:
            payload = json.loads(legacy_file.read_text(encoding="utf-8"))
        except Exception:
            return

        message = payload.get("message")
        if not message:
            return

        with database.connection() as conn:
            conn.execute(
                """
                INSERT INTO notifications (message, kind, send_time, is_active, created_at)
                VALUES (?, 'manual', NULL, 0, ?)
                """,
                (message, now_iso()),
            )

    def _parse_days(self, raw_days) -> tuple[int, ...]:
        if raw_days is None or raw_days == "":
            return tuple()

        if isinstance(raw_days, int):
            if 0 <= raw_days <= 6:
                return (raw_days,)
            return tuple()

        days = []
        for item in str(raw_days).split(","):
            item = item.strip()
            if not item:
                continue
            try:
                value = int(item)
            except ValueError:
                continue
            if 0 <= value <= 6:
                days.append(value)

        return tuple(sorted(set(days)))

    def _render_message_for_user(self, message: str, user: dict) -> str:
        raw_username = (user.get("username") or "").strip()
        full_name = (user.get("full_name") or "").strip()
        first_name = full_name.split()[0] if full_name else raw_username or "there"
        safe_name = full_name or first_name or raw_username or "there"
        safe_username = f"@{raw_username}" if raw_username else first_name

        rendered = message
        rendered = rendered.replace("{name}", safe_name)
        rendered = rendered.replace("{username}", safe_username)
        rendered = rendered.replace("{first_name}", first_name)
        return rendered

    def _job_name(self, notification_id: int) -> str:
        return f"notification:{notification_id}"

    def _remove_scheduled_job(self, notification_id: int):
        if not self.application:
            return

        name = self._job_name(notification_id)
        for job in self.application.job_queue.get_jobs_by_name(name):
            job.schedule_removal()

    def _server_now(self) -> datetime:
        return datetime.now().astimezone()

    def _india_now(self) -> datetime:
        return datetime.now(INDIA_TZ)

    def _ensure_broadcast_worker(self):
        if self._broadcast_queue is None:
            self._broadcast_queue = asyncio.Queue(maxsize=10)

        if self._broadcast_worker_task and not self._broadcast_worker_task.done():
            return

        self._broadcast_worker_task = asyncio.create_task(self._broadcast_worker())

    async def _broadcast_worker(self):
        logger.info("Notification broadcast worker started")
        while True:
            payload = await self._broadcast_queue.get()
            try:
                sent, failed = await self.broadcast(payload["message"])
                notification_id = payload.get("notification_id")
                if notification_id:
                    with database.connection() as conn:
                        conn.execute(
                            "UPDATE notifications SET last_sent_at = ? WHERE notification_id = ?",
                            (now_iso(), notification_id),
                        )
                logger.info(
                    "Notification worker completed | source=%s notification_id=%s sent=%s failed=%s",
                    payload.get("source"),
                    notification_id,
                    sent,
                    failed,
                )
            except Exception as exc:
                logger.exception(
                    "Notification worker failed | source=%s notification_id=%s reason=%s",
                    payload.get("source"),
                    payload.get("notification_id"),
                    exc,
                )
            finally:
                self._broadcast_queue.task_done()


notification_service = NotificationService()
