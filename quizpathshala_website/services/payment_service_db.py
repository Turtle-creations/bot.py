import os
import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone

import httpx

from config import (
    BOT_USERNAME,
    PUBLIC_BASE_URL,
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
)
from db.database import database
from services.user_service_db import now_iso, parse_utc_datetime, user_service
from utils.logging_utils import get_logger


SUBSCRIPTION_PLANS = {
    "week_1": {"name": "1 Week", "amount": 9900, "days": 7},
    "month_1": {"name": "1 Month", "amount": 29900, "days": 30},
    "months_3": {"name": "3 Months", "amount": 79900, "days": 90},
    "year_1": {"name": "1 Year", "amount": 249900, "days": 365},
}

PREMIUM_PRICE_PLAN_ALIASES = {
    "week_1": "week_1",
    "month_1": "month_1",
    "month_3": "months_3",
    "months_3": "months_3",
}


logger = get_logger(__name__)
MAX_WEBHOOK_DUPLICATE_COUNT = 5
PREMIUM_ACTIVATION_SOURCE_WEBHOOK = "razorpay_webhook"


class PaymentService:
    def _normalize_price_plan_type(self, plan_type: str) -> str | None:
        return PREMIUM_PRICE_PLAN_ALIASES.get((plan_type or "").strip().lower())

    def _price_setting_key(self, plan_type: str) -> str:
        normalized = self._normalize_price_plan_type(plan_type)
        if not normalized:
            raise ValueError("Invalid premium plan")
        return f"premium_price:{normalized}"

    def _get_setting_value(self, key: str) -> str | None:
        with database.connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def _set_setting_value(self, key: str, value: str) -> None:
        with database.connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now_iso()),
            )

    def get_plan(self, plan_type: str) -> dict:
        if plan_type not in SUBSCRIPTION_PLANS:
            raise ValueError("Invalid plan selected")

        plan = dict(SUBSCRIPTION_PLANS[plan_type])
        if plan_type in {"week_1", "month_1", "months_3"}:
            stored_value = self._get_setting_value(self._price_setting_key(plan_type))
            if stored_value is not None:
                plan["amount"] = int(stored_value)
                logger.info(
                    "premium_price_loaded_from_settings | plan_type=%s amount_paise=%s amount_rupees=%s",
                    plan_type,
                    plan["amount"],
                    f"{Decimal(int(plan['amount'])) / Decimal('100'):.2f}",
                )
        return plan

    def list_checkout_plans(self) -> list[dict]:
        plans = []
        for plan_type in ("week_1", "month_1", "months_3", "year_1"):
            plan = self.get_plan(plan_type)
            plans.append(
                {
                    "plan_type": plan_type,
                    "name": plan["name"],
                    "days": plan["days"],
                    "amount": int(plan["amount"]),
                    "amount_rupees": Decimal(int(plan["amount"])) / Decimal("100"),
                }
            )
        return plans

    def list_premium_prices(self) -> list[dict]:
        items = []
        for display_key, internal_key in (("week_1", "week_1"), ("month_1", "month_1"), ("month_3", "months_3")):
            plan = self.get_plan(internal_key)
            items.append(
                {
                    "key": display_key,
                    "plan_type": internal_key,
                    "name": plan["name"],
                    "amount_paise": int(plan["amount"]),
                    "amount_rupees": Decimal(int(plan["amount"])) / Decimal("100"),
                }
            )
        return items

    def update_premium_price(self, plan_type: str, amount_text: str) -> dict:
        normalized_plan_type = self._normalize_price_plan_type(plan_type)
        if normalized_plan_type not in {"week_1", "month_1", "months_3"}:
            raise ValueError("Invalid premium plan. Use week_1, month_1, or month_3.")

        try:
            amount_rupees = Decimal((amount_text or "").strip())
        except InvalidOperation as exc:
            raise ValueError("Amount must be numeric.") from exc

        if amount_rupees < Decimal("1"):
            raise ValueError("Amount must be at least 1.")

        amount_paise = int((amount_rupees * Decimal("100")).quantize(Decimal("1")))
        self._set_setting_value(self._price_setting_key(normalized_plan_type), str(amount_paise))
        plan = self.get_plan(normalized_plan_type)
        logger.info(
            "premium_price_updated | plan_type=%s amount_paise=%s amount_rupees=%s",
            normalized_plan_type,
            amount_paise,
            f"{Decimal(amount_paise) / Decimal('100'):.2f}",
        )
        return {
            "display_plan_type": "month_3" if normalized_plan_type == "months_3" else normalized_plan_type,
            "plan_type": normalized_plan_type,
            "name": plan["name"],
            "amount_paise": amount_paise,
            "amount_rupees": Decimal(amount_paise) / Decimal("100"),
        }

    def _compute_premium_expiry(self, user: dict, plan_type: str) -> str:
        plan = self.get_plan(plan_type)
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
        return (start + timedelta(days=plan["days"])).replace(microsecond=0).isoformat()

    def ensure_premium_active_for_order(self, order_id: str, *, source: str | None = None) -> dict:
        logger.info(
            "premium_activation_attempt | order_id=%s source=%s",
            order_id,
            source,
        )
        logger.info("premium activation start | order_id=%s source=%s", order_id, source)
        if source != PREMIUM_ACTIVATION_SOURCE_WEBHOOK:
            logger.warning(
                "premium_activation_blocked_non_webhook | order_id=%s source=%s",
                order_id,
                source,
            )
            logger.info(
                "premium activation end | order_id=%s ok=%s reason=%s",
                order_id,
                False,
                "non_webhook_source",
            )
            return {"ok": False, "reason": "non_webhook_source", "activated_now": False}
        order = self.get_order(order_id)
        if not order:
            logger.info("premium activation end | order_id=%s ok=%s reason=%s", order_id, False, "order_not_found")
            return {"ok": False, "reason": "order_not_found"}
        result = self.ensure_premium_active_for_order_data(order, source=source)
        logger.info(
            "premium activation end | order_id=%s ok=%s reason=%s activated_now=%s",
            order_id,
            result.get("ok"),
            result.get("reason"),
            result.get("activated_now"),
        )
        return result

    def ensure_premium_active_for_order_data(self, order_data: dict, *, source: str | None = None) -> dict:
        if source != PREMIUM_ACTIVATION_SOURCE_WEBHOOK:
            logger.warning(
                "premium_activation_blocked_non_webhook | order_id=%s source=%s",
                order_data.get("order_id"),
                source,
            )
            return {"ok": False, "reason": "non_webhook_source", "activated_now": False}

        plan_type = order_data.get("plan_type")
        if plan_type not in SUBSCRIPTION_PLANS:
            return {"ok": True, "reason": "non_premium_plan", "activated_now": False}

        user_id = order_data["user_id"]
        user = user_service.get_user(user_id)
        if not user:
            logger.warning(
                "Premium activation skipped | order_id=%s user_id=%s reason=user_not_found",
                order_data.get("order_id"),
                user_id,
            )
            return {"ok": False, "reason": "user_not_found"}

        premium_active = bool(user.get("is_premium")) and bool(user.get("premium_expires_at"))
        if premium_active:
            expiry_dt = parse_utc_datetime(user["premium_expires_at"])
            if expiry_dt and expiry_dt > datetime.now(timezone.utc):
                return {
                    "ok": True,
                    "reason": "already_active",
                    "activated_now": False,
                    "expiry": user["premium_expires_at"],
                }

        expiry = self._compute_premium_expiry(user, plan_type)
        user_service.set_premium_expiry(user_id, expiry, True)
        logger.info(
            "premium_activation_success | order_id=%s user_id=%s plan_type=%s final_order_status=%s expiry=%s",
            order_data.get("order_id"),
            user_id,
            plan_type,
            order_data.get("status"),
            expiry,
        )
        return {
            "ok": True,
            "reason": "activated",
            "activated_now": True,
            "expiry": expiry,
            "user_id": user_id,
            "plan_type": plan_type,
        }

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
        if not (BOT_USERNAME or "").strip() or (BOT_USERNAME or "").strip() == "YOUR_BOT_USERNAME":
            missing.append("BOT_USERNAME")

        return missing

    def set_order_status_if_not_paid(self, order_id: str, status: str) -> tuple[dict | None, bool]:
        with database.connection() as conn:
            row = conn.execute(
                "SELECT * FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not row:
                return None, False

            order = dict(row)
            if order.get("status") == "paid":
                return order, False

            conn.execute(
                "UPDATE payment_orders SET status = ? WHERE order_id = ?",
                (status, order_id),
            )
            updated_row = conn.execute(
                "SELECT * FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        return dict(updated_row) if updated_row else order, True

    async def create_order(self, user_id: int, plan_type: str) -> dict:
        if plan_type not in SUBSCRIPTION_PLANS:
            raise ValueError("Invalid plan selected")

        missing = self.get_missing_configuration()
        if missing:
            raise ValueError(f"Missing required payment env vars: {', '.join(missing)}")

        plan = self.get_plan(plan_type)
        logger.info(
            "premium_price_used_for_order | user_id=%s plan_type=%s amount_paise=%s amount_rupees=%s",
            user_id,
            plan_type,
            plan["amount"],
            f"{Decimal(int(plan['amount'])) / Decimal('100'):.2f}",
        )
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

    def get_order_with_fallback_sync(self, order_id: str) -> tuple[dict | None, str]:
        order = self.get_order(order_id)
        if order:
            return order, "database"

        remote_order = self.fetch_razorpay_order_sync(order_id)
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

    def fetch_razorpay_payment_sync(self, payment_id: str) -> dict | None:
        if not payment_id or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            return None

        with httpx.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = client.get(f"https://api.razorpay.com/v1/payments/{payment_id}")
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

    def fetch_razorpay_order_sync(self, order_id: str) -> dict | None:
        if not order_id or not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
            return None

        with httpx.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = client.get(f"https://api.razorpay.com/v1/orders/{order_id}")
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
        payment_status = payment_entity.get("status")

        if not payment_id or not order_id or amount is None:
            raise ValueError("Missing payment fields in webhook payload")
        if payment_status != "captured":
            raise ValueError("Webhook payment status is not captured")

        with database.connection() as conn:
            duplicate_status = self._get_duplicate_status(conn, event_id=event_id, payment_id=payment_id, order_id=order_id)
            order = conn.execute(
                "SELECT * FROM payment_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            if not order:
                raise ValueError("Order not found for captured payment")

            order_data = dict(order)
            if duplicate_status["duplicate"]:
                self._record_duplicate_attempt(
                    conn,
                    event_id=event_id,
                    payment_id=payment_id,
                    order_id=order_id,
                    existing_event=duplicate_status["existing_event"],
                )
                logger.info(
                    "Duplicate webhook already processed | event_id=%s order_id=%s payment_id=%s reason=%s duplicate_count=%s",
                    event_id,
                    order_id,
                    payment_id,
                    duplicate_status["reason"],
                    duplicate_status["duplicate_count"],
                )
                return {
                    "status": "already_processed",
                    "reason": duplicate_status["reason"],
                    "user_id": order_data["user_id"],
                    "plan_type": order_data["plan_type"],
                }

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
                user = user_service.get_user(order_data["user_id"])
                if not user:
                    logger.warning(
                        "Webhook user not found | event_id=%s order_id=%s user_id=%s",
                        event_id,
                        order_id,
                        order_data["user_id"],
                    )
                    raise ValueError("User not found for captured payment")
                expiry = self._compute_premium_expiry(user, plan_type)

            conn.execute(
                """
                INSERT INTO processed_webhooks (
                    event_id, payment_id, order_id, received_at, last_seen_at, duplicate_count
                ) VALUES (?, ?, ?, ?, ?, 0)
                """,
                (event_id, payment_id, order_id, now_iso(), now_iso()),
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
                    payment_status,
                    now_iso(),
                    expiry,
                    json.dumps(payload),
                ),
            )
            conn.execute(
                "UPDATE payment_orders SET status = ? WHERE order_id = ?",
                ("paid", order_id),
            )

        activation_result = self.ensure_premium_active_for_order(
            order_id,
            source=PREMIUM_ACTIVATION_SOURCE_WEBHOOK,
        )
        if not should_activate_premium:
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
            "activation_result": activation_result,
        }

    def check_processed_webhook(self, event_id: str, payment_id: str | None, order_id: str | None) -> dict:
        with database.connection() as conn:
            duplicate_status = self._get_duplicate_status(
                conn,
                event_id=event_id,
                payment_id=payment_id,
                order_id=order_id,
            )
            if not duplicate_status["duplicate"]:
                return {"duplicate": False}

            self._record_duplicate_attempt(
                conn,
                event_id=event_id,
                payment_id=payment_id,
                order_id=order_id,
                existing_event=duplicate_status["existing_event"],
            )
            return duplicate_status

    def _get_duplicate_status(self, conn, *, event_id: str, payment_id: str | None, order_id: str | None) -> dict:
        event_row = conn.execute(
            "SELECT event_id, duplicate_count FROM processed_webhooks WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if event_row:
            return {
                "duplicate": True,
                "reason": "duplicate_event",
                "existing_event": event_row["event_id"],
                "duplicate_count": min(int(event_row["duplicate_count"] or 0) + 1, MAX_WEBHOOK_DUPLICATE_COUNT),
            }

        payment_row = None
        if payment_id or order_id:
            payment_row = conn.execute(
                """
                SELECT payment_id, order_id
                FROM payments
                WHERE (? IS NOT NULL AND payment_id = ?)
                   OR (? IS NOT NULL AND order_id = ?)
                """,
                (payment_id, payment_id, order_id, order_id),
            ).fetchone()
        if payment_row:
            return {
                "duplicate": True,
                "reason": "payment_exists",
                "existing_event": None,
                "duplicate_count": 1,
            }

        return {"duplicate": False}

    def _record_duplicate_attempt(
        self,
        conn,
        *,
        event_id: str,
        payment_id: str | None,
        order_id: str | None,
        existing_event: str | None,
    ) -> None:
        timestamp = now_iso()
        target_event_id = existing_event or event_id
        current_row = conn.execute(
            "SELECT duplicate_count FROM processed_webhooks WHERE event_id = ?",
            (target_event_id,),
        ).fetchone()
        if current_row:
            next_count = min(int(current_row["duplicate_count"] or 0) + 1, MAX_WEBHOOK_DUPLICATE_COUNT)
            conn.execute(
                """
                UPDATE processed_webhooks
                SET last_seen_at = ?, duplicate_count = ?, payment_id = COALESCE(payment_id, ?), order_id = COALESCE(order_id, ?)
                WHERE event_id = ?
                """,
                (timestamp, next_count, payment_id, order_id, target_event_id),
            )
            return

        conn.execute(
            """
            INSERT INTO processed_webhooks (
                event_id, payment_id, order_id, received_at, last_seen_at, duplicate_count
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (event_id, payment_id, order_id, timestamp, timestamp),
        )

    def premium_status_text(self, user: dict) -> str:
        expiry = parse_utc_datetime(user.get("premium_expires_at"))
        if user.get("is_premium") and expiry and expiry > datetime.now(timezone.utc):
            return f"💎 Premium active until {expiry.replace(microsecond=0).isoformat()} UTC"
        return "🆓 Free plan active"


payment_service = PaymentService()
