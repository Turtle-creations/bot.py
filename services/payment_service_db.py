import os
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx

from config import (
    PUBLIC_BASE_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
)
from db.database import database
from services.user_service_db import now_iso, user_service
from utils.logging_utils import get_logger


SUBSCRIPTION_PLANS = {
    "week_1": {"name": "1 Week", "amount": 9900, "days": 7},
    "month_1": {"name": "1 Month", "amount": 29900, "days": 30},
    "months_3": {"name": "3 Months", "amount": 79900, "days": 90},
    "year_1": {"name": "1 Year", "amount": 249900, "days": 365},
}


logger = get_logger(__name__)


class PaymentService:
    def _save_order_record(
        self,
        *,
        order_id: str,
        user_id: int,
        plan_type: str,
        amount: int,
        currency: str,
        status: str,
        payment_url: str,
    ):
        database.initialize()
        with database.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO payment_orders (
                    order_id, user_id, plan_type, amount, currency, status, payment_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    user_id,
                    plan_type,
                    amount,
                    currency,
                    status,
                    payment_url,
                    now_iso(),
                ),
            )
            saved_row = conn.execute(
                """
                SELECT order_id, user_id, plan_type, amount, currency, status, payment_url, created_at
                FROM payment_orders
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
        logger.info(
            "Payment order saved | order_id=%s row_exists=%s user_id=%s plan_type=%s amount=%s currency=%s status=%s",
            order_id,
            bool(saved_row),
            user_id,
            plan_type,
            amount,
            currency,
            status,
        )

    def get_missing_configuration(self) -> list[str]:
        missing = []

        if not (RAZORPAY_KEY_ID or "").strip():
            missing.append("RAZORPAY_KEY_ID")
        if not (RAZORPAY_KEY_SECRET or "").strip():
            missing.append("RAZORPAY_KEY_SECRET")
        if not (RAZORPAY_WEBHOOK_SECRET or "").strip():
            missing.append("RAZORPAY_WEBHOOK_SECRET")
        if not (os.getenv("PUBLIC_BASE_URL", "") or "").strip():
            missing.append("PUBLIC_BASE_URL")

        return missing

    async def create_order(self, user_id: int, plan_type: str) -> dict:
        if plan_type not in SUBSCRIPTION_PLANS:
            raise ValueError("Invalid plan selected")

        missing = self.get_missing_configuration()
        if missing:
            raise ValueError(f"Missing required payment env vars: {', '.join(missing)}")

        plan = SUBSCRIPTION_PLANS[plan_type]
        payload = {
            "amount": plan["amount"],
            "currency": "INR",
            "receipt": f"quizbot_{user_id}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user_id),
                "plan_type": plan_type,
            },
        }

        async with httpx.AsyncClient(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = await client.post("https://api.razorpay.com/v1/orders", json=payload)
            response.raise_for_status()
            order = response.json()

        payment_url = f"{PUBLIC_BASE_URL}/pay/{order['id']}"
        self._save_order_record(
            order_id=order["id"],
            user_id=user_id,
            plan_type=plan_type,
            amount=plan["amount"],
            currency=order.get("currency", "INR"),
            status=order.get("status", "created"),
            payment_url=payment_url,
        )

        return {
            "order_id": order["id"],
            "payment_url": payment_url,
            "plan_name": plan["name"],
            "amount": plan["amount"],
            "currency": "INR",
        }

    async def create_test_order(self, user_id: int) -> dict:
        if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            raise ValueError("Razorpay credentials are not configured")

        payload = {
            "amount": 100,
            "currency": "INR",
            "receipt": f"quizbot_test_{user_id}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "user_id": str(user_id),
                "purpose": "admin_test_order",
            },
        }

        async with httpx.AsyncClient(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = await client.post("https://api.razorpay.com/v1/orders", json=payload)
            response.raise_for_status()
            order = response.json()

        payment_url = f"{PUBLIC_BASE_URL}/pay/{order['id']}"
        self._save_order_record(
            order_id=order["id"],
            user_id=user_id,
            plan_type="test_order",
            amount=payload["amount"],
            currency=order.get("currency", "INR"),
            status=order.get("status", "created"),
            payment_url=payment_url,
        )

        return {
            "order_id": order["id"],
            "payment_url": payment_url,
            "plan_name": "Test Payment Order",
            "amount": payload["amount"],
            "currency": payload["currency"],
        }

    def get_order(self, order_id: str) -> dict | None:
        with database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        return dict(row) if row else None

    async def get_order_with_fallback(self, order_id: str) -> tuple[dict | None, str]:
        order = self.get_order(order_id)
        if order:
            return order, "database"

        remote_order = await self.fetch_razorpay_order(order_id)
        if not remote_order:
            return None, "missing"

        notes = remote_order.get("notes") or {}
        user_id_raw = notes.get("user_id")
        plan_type = notes.get("plan_type") or notes.get("purpose") or "unknown"
        if not str(user_id_raw or "").isdigit():
            logger.warning(
                "Remote order cannot be restored locally | order_id=%s reason=missing_user_id notes=%s",
                order_id,
                notes,
            )
            return None, "razorpay_missing_user_id"

        payment_url = f"{PUBLIC_BASE_URL}/pay/{remote_order['id']}"
        self._save_order_record(
            order_id=remote_order["id"],
            user_id=int(user_id_raw),
            plan_type=plan_type,
            amount=int(remote_order.get("amount") or 0),
            currency=remote_order.get("currency", "INR"),
            status=remote_order.get("status", "created"),
            payment_url=payment_url,
        )
        restored_order = self.get_order(order_id)
        if restored_order:
            logger.info(
                "Payment order restored from Razorpay | order_id=%s user_id=%s plan_type=%s",
                order_id,
                user_id_raw,
                plan_type,
            )
            return restored_order, "razorpay_restored"

        return None, "razorpay_restore_failed"

    def update_order_status(self, order_id: str, status: str):
        with database.connection() as conn:
            conn.execute(
                "UPDATE payment_orders SET status = ? WHERE order_id = ?",
                (status, order_id),
            )

    async def fetch_razorpay_payment(self, payment_id: str) -> dict | None:
        if not payment_id or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            return None

        async with httpx.AsyncClient(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = await client.get(f"https://api.razorpay.com/v1/payments/{payment_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def fetch_razorpay_order(self, order_id: str) -> dict | None:
        if not order_id or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            return None

        async with httpx.AsyncClient(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = await client.get(f"https://api.razorpay.com/v1/orders/{order_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not RAZORPAY_WEBHOOK_SECRET:
            return False

        expected = hmac.new(
            RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_payment_signature(
        self,
        *,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        if not RAZORPAY_KEY_SECRET:
            return False

        expected = hmac.new(
            RAZORPAY_KEY_SECRET.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def process_captured_payment(self, event_id: str, payload: dict):
        event_name = payload.get("event")
        if event_name != "payment.captured":
            logger.info("Ignoring webhook event | event_id=%s event=%s", event_id, event_name)
            return {"status": "ignored", "reason": "unsupported_event"}

        payment_entity = (
            payload.get("payload", {})
            .get("payment", {})
            .get("entity", {})
        )

        payment_id = payment_entity.get("id")
        order_id = payment_entity.get("order_id")
        amount = payment_entity.get("amount")
        currency = payment_entity.get("currency", "INR")

        if not payment_id or not order_id or amount is None:
            raise ValueError("Missing payment fields in webhook payload")

        with database.connection() as conn:
            existing = conn.execute(
                "SELECT event_id FROM processed_webhooks WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing:
                logger.info("Duplicate webhook ignored | event_id=%s order_id=%s", event_id, order_id)
                return {"status": "ignored", "reason": "duplicate_event"}

            order = conn.execute(
                "SELECT * FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not order:
                raise ValueError("Order not found for captured payment")

            order_data = dict(order)
            expected_amount = order_data["amount"]
            if amount != expected_amount:
                logger.warning(
                    "Webhook amount mismatch | event_id=%s order_id=%s expected_amount=%s received_amount=%s",
                    event_id,
                    order_id,
                    expected_amount,
                    amount,
                )
                raise ValueError("Payment amount does not match the saved order")

            plan_type = order_data["plan_type"]
            expiry = now_iso()
            should_activate_premium = plan_type in SUBSCRIPTION_PLANS

            if should_activate_premium:
                plan = SUBSCRIPTION_PLANS[plan_type]
                user = user_service.get_user(order_data["user_id"])
                if not user:
                    logger.warning(
                        "Webhook user not found | event_id=%s order_id=%s user_id=%s",
                        event_id,
                        order_id,
                        order_data["user_id"],
                    )
                    raise ValueError("User not found for captured payment")

                now = datetime.now(timezone.utc)
                current_expiry = user.get("premium_expires_at")
                if current_expiry:
                    try:
                        current_dt = datetime.fromisoformat(current_expiry)
                        if current_dt.tzinfo is None:
                            current_dt = current_dt.replace(tzinfo=timezone.utc)
                        start = current_dt if current_dt > now else now
                    except ValueError:
                        start = now
                else:
                    start = now

                expiry = (start + timedelta(days=plan["days"])).replace(microsecond=0).isoformat()

            conn.execute(
                "INSERT INTO processed_webhooks (event_id, received_at) VALUES (?, ?)",
                (event_id, now_iso()),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO payments (
                    payment_id, order_id, user_id, plan_type, amount, currency, status,
                    timestamp, expiry_date, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_id,
                    order_id,
                    order_data["user_id"],
                    plan_type,
                    amount,
                    currency,
                    payment_entity.get("status", "captured"),
                    now_iso(),
                    expiry,
                    json.dumps(payload),
                ),
            )
            conn.execute(
                "UPDATE payment_orders SET status = ? WHERE order_id = ?",
                ("paid", order_id),
            )

        if should_activate_premium:
            user_service.set_premium_expiry(order_data["user_id"], expiry, True)
            logger.info(
                "Premium activation success | event_id=%s order_id=%s user_id=%s plan_type=%s expiry=%s",
                event_id,
                order_id,
                order_data["user_id"],
                plan_type,
                expiry,
            )
        else:
            logger.info(
                "Webhook payment recorded without premium activation | event_id=%s order_id=%s plan_type=%s",
                event_id,
                order_id,
                plan_type,
            )

        return {
            "status": "processed",
            "user_id": order_data["user_id"],
            "plan_type": plan_type,
            "expiry": expiry,
        }

    def premium_status_text(self, user: dict) -> str:
        if user.get("is_premium") and user.get("premium_expires_at"):
            return f"💎 Premium active until {user['premium_expires_at']} UTC"
        return "🆓 Free plan active"


payment_service = PaymentService()
