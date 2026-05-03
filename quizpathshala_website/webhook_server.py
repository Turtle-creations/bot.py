from pathlib import Path

from flask import Flask, render_template

from config import BASE_DIR, BOT_URL, CANONICAL_URL, SECRET_KEY, SITE_NAME, SITE_TAGLINE, SUPPORT_EMAIL, SUPPORT_HOURS, SUPPORT_TELEGRAM


WEBSITE_DIR = BASE_DIR / "website"
WEBSITE_TEMPLATES = WEBSITE_DIR / "templates"
WEBSITE_STATIC = WEBSITE_DIR / "static"

app = Flask(
    __name__,
    template_folder=str(WEBSITE_TEMPLATES),
    static_folder=str(WEBSITE_STATIC),
    static_url_path="/static",
)
app.config["SECRET_KEY"] = SECRET_KEY


def _context() -> dict:
    return {
        "site_name": SITE_NAME,
        "tagline": SITE_TAGLINE,
        "bot_url": BOT_URL,
        "support_email": SUPPORT_EMAIL,
        "support_hours": SUPPORT_HOURS,
        "support_telegram": SUPPORT_TELEGRAM,
        "canonical_url": CANONICAL_URL,
    }


@app.route("/")
def home():
    return render_template("home.html", page_title="Home", **_context())


@app.route("/privacy")
def privacy():
    page = {
        "title": "Privacy Policy",
        "intro": "QuizPathshala uses only the information needed to support learning access, premium coordination, and support communication.",
        "sections": [
            "We may collect basic contact details, Telegram identifiers, and payment references when needed for support.",
            "Your information is used only for operating QuizPathshala, handling support requests, and improving the service.",
            "QuizPathshala does not intentionally expose personal information, bot tokens, or payment secrets on this website.",
        ],
    }
    return render_template("simple_page.html", page_title=page["title"], page=page, **_context())


@app.route("/terms")
def terms():
    page = {
        "title": "Terms & Conditions",
        "intro": "By using QuizPathshala, you agree to use the platform responsibly for lawful educational purposes.",
        "sections": [
            "QuizPathshala may update content, features, and pricing when needed.",
            "Premium access follows the selected plan and payment verification process.",
            "Users must not misuse the platform, attempt unauthorized access, or redistribute protected content.",
        ],
    }
    return render_template("simple_page.html", page_title=page["title"], page=page, **_context())


@app.route("/refund-policy")
def refund_policy():
    page = {
        "title": "Refund Policy",
        "intro": "QuizPathshala reviews genuine payment and activation issues as quickly as possible.",
        "sections": [
            "If a payment is completed but premium access is not activated after verification, contact support with your payment reference.",
            "Verified duplicate charges or failed activations may be reviewed for refund or manual correction.",
            "Approved refunds are processed through the original payment method according to provider and banking timelines.",
        ],
    }
    return render_template("simple_page.html", page_title=page["title"], page=page, **_context())


@app.route("/contact")
def contact():
    return render_template("contact.html", page_title="Contact", **_context())
