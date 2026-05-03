import random

from flask import session

from services.user_service_db import user_service


class WebIdentityService:
    SESSION_KEY = "web_user_id"
    ADMIN_KEY = "admin_authenticated"

    def get_or_create_user(self) -> dict:
        user_id = session.get(self.SESSION_KEY)
        if not user_id:
            user_id = self._generate_user_id()
            session[self.SESSION_KEY] = user_id

        full_name = session.get("web_user_name") or f"Guest {str(user_id)[-6:]}"
        session["web_user_name"] = full_name
        return user_service.ensure_profile(
            user_id=int(user_id),
            full_name=full_name,
            username=None,
            is_admin=self.is_admin_authenticated(),
        )

    def update_name(self, full_name: str) -> dict:
        cleaned = (full_name or "").strip() or "Guest User"
        session["web_user_name"] = cleaned
        user_id = int(session[self.SESSION_KEY])
        return user_service.ensure_profile(
            user_id=user_id,
            full_name=cleaned,
            username=None,
            is_admin=self.is_admin_authenticated(),
        )

    def mark_admin_authenticated(self) -> None:
        session[self.ADMIN_KEY] = True
        if self.SESSION_KEY in session:
            current = self.get_or_create_user()
            user_service.ensure_profile(
                user_id=current["user_id"],
                full_name=current["full_name"],
                username=current.get("username"),
                is_admin=True,
            )

    def clear_admin_authenticated(self) -> None:
        session.pop(self.ADMIN_KEY, None)

    def is_admin_authenticated(self) -> bool:
        return bool(session.get(self.ADMIN_KEY))

    def _generate_user_id(self) -> int:
        return random.randint(7000000000, 7999999999)


web_identity_service = WebIdentityService()
