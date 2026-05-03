import time
from decimal import Decimal

import httpx

from config import PUBLIC_BASE_URL, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from db.database import database
from services.payment_service_db import payment_service
from services.user_service_db import now_iso


class WebPaymentService:
    def create_order(self, user_id: int, plan_type: str) -> dict:
        if plan_type not in {"week_1", "month_1", "months_3"}:
            raise ValueError("Invalid premium plan selected.")

        missing = payment_service.get_missing_configuration()
        if missing:
            raise ValueError(f"Missing required payment env vars: {', '.join(missing)}")

        plan = payment_service.get_plan(plan_type)
        payload = {
            "amount": plan["amount"],
            "currency": "INR",
            "receipt": f"quizpathshala_{user_id}_{int(time.time())}",
            "notes": {
                "user_id": str(user_id),
                "plan_type": plan_type,
            },
        }

        with httpx.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET), timeout=20) as client:
            response = client.post("https://api.razorpay.com/v1/orders", json=payload)
            response.raise_for_status()
            order = response.json()

        payment_url = f"{PUBLIC_BASE_URL}/payment/{order['id']}"
        with database.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO payment_orders (
                    order_id, user_id, plan_type, amount, currency, status, payment_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["id"],
                    user_id,
                    plan_type,
                    plan["amount"],
                    order.get("currency", "INR"),
                    order.get("status", "created"),
                    payment_url,
                    now_iso(),
                ),
            )

        return {
            "order_id": order["id"],
            "payment_url": payment_url,
            "plan_name": plan["name"],
            "amount": plan["amount"],
            "amount_rupees": Decimal(int(plan["amount"])) / Decimal("100"),
            "currency": order.get("currency", "INR"),
        }

    def list_orders(self, limit: int = 50) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM payment_orders
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_payments(self, limit: int = 50) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM payments
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]


web_payment_service = WebPaymentService()
