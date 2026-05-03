from flask import Blueprint, flash, redirect, render_template, request, url_for

from config import BOT_URL, CANONICAL_URL, SITE_NAME, SITE_TAGLINE, SUPPORT_EMAIL, SUPPORT_HOURS, SUPPORT_TELEGRAM
from services.site_content import FEATURE_ITEMS, LEGAL_PAGES
from services.web_admin_service import web_admin_service
from services.web_identity_service import web_identity_service
from services.web_quiz_service import web_quiz_service


pages_blueprint = Blueprint("pages", __name__)


def _shared_context() -> dict:
    user = web_identity_service.get_or_create_user()
    return {
        "site_name": SITE_NAME,
        "tagline": SITE_TAGLINE,
        "bot_url": BOT_URL,
        "support_email": SUPPORT_EMAIL,
        "support_hours": SUPPORT_HOURS,
        "support_telegram": SUPPORT_TELEGRAM,
        "canonical_url": CANONICAL_URL,
        "features": FEATURE_ITEMS,
        "user": user,
        "catalog": web_quiz_service.list_exam_catalog(user["user_id"]),
        "admin_authenticated": web_identity_service.is_admin_authenticated(),
    }


@pages_blueprint.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        full_name = request.form.get("full_name", "")
        web_identity_service.update_name(full_name)
        flash("Your display name was updated for this session.", "success")
        return redirect(url_for("pages.home"))

    return render_template("home.html", **_shared_context(), page_title="Home")


@pages_blueprint.route("/contact", methods=["GET", "POST"])
def contact():
    user = web_identity_service.get_or_create_user()
    if request.method == "POST":
        message_text = (request.form.get("message") or "").strip()
        full_name = (request.form.get("full_name") or "").strip()
        if full_name:
            user = web_identity_service.update_name(full_name)
        if not message_text:
            flash("Please write a support message before submitting.", "error")
        else:
            ticket_id = web_admin_service.create_support_ticket(user, message_text)
            flash(f"Support ticket #{ticket_id} created successfully.", "success")
            return redirect(url_for("pages.contact"))

    page = {
        "title": "Contact & Support",
        "intro": "Need help with quiz access, premium status, or general support? Reach out directly and the QuizPathshala team can review your request.",
        "sections": [
            f"Telegram support: {SUPPORT_TELEGRAM}",
            f"Email support: {SUPPORT_EMAIL}",
            f"Support hours: {SUPPORT_HOURS}",
        ],
    }
    return render_template("contact.html", **_shared_context(), page_title=page["title"], page=page)


@pages_blueprint.route("/privacy")
def privacy():
    return render_template("simple_page.html", **_shared_context(), page_title="Privacy Policy", page=LEGAL_PAGES["privacy"])


@pages_blueprint.route("/terms")
def terms():
    return render_template("simple_page.html", **_shared_context(), page_title="Terms & Conditions", page=LEGAL_PAGES["terms"])


@pages_blueprint.route("/refund-policy")
def refund_policy():
    return render_template("simple_page.html", **_shared_context(), page_title="Refund Policy", page=LEGAL_PAGES["refund-policy"])


@pages_blueprint.route("/health")
def health():
    return {"status": "ok", "service": "quizpathshala-web"}
