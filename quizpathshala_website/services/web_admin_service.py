from db.database import database
from services.payment_service_db import payment_service
from services.support_service_db import support_service
from services.user_service_db import user_service
from services.web_payment_service import web_payment_service


class WebAdminService:
    def dashboard_data(self) -> dict:
        return {
            "users": user_service.list_users(),
            "payments": web_payment_service.list_payments(),
            "orders": web_payment_service.list_orders(),
            "premium_prices": payment_service.list_premium_prices(),
            "support_tickets": self.list_support_tickets(),
        }

    def list_support_tickets(self, limit: int = 50) -> list[dict]:
        with database.connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM support_messages
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_support_ticket(self, user: dict, message_text: str) -> int:
        return support_service.create_ticket(user, message_text)


web_admin_service = WebAdminService()
