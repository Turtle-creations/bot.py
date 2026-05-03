from flask import Flask, abort, send_file

from config import (
    BASE_DIR,
    BOT_URL,
    CANONICAL_URL,
    PORT,
    SECRET_KEY,
    SITE_NAME,
    SITE_TAGLINE,
    STATIC_DIR,
    SUPPORT_HOURS,
    SUPPORT_TELEGRAM,
    TEMPLATES_DIR,
)
from db.database import database
from routes.admin import admin_blueprint
from routes.pages import pages_blueprint
from routes.premium import premium_blueprint
from routes.quiz import quiz_blueprint
from services.bootstrap_service import bootstrap_application
from utils.logging_utils import get_logger, setup_logging


logger = get_logger(__name__)
MEDIA_ROOT = (BASE_DIR / "data").resolve()


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
        static_url_path="/static",
    )
    app.config["SECRET_KEY"] = SECRET_KEY

    database.initialize()
    bootstrap_application()

    @app.context_processor
    def inject_site_context():
        return {
            "site_name": SITE_NAME,
            "tagline": SITE_TAGLINE,
            "bot_url": BOT_URL,
            "support_hours": SUPPORT_HOURS,
            "support_telegram": SUPPORT_TELEGRAM,
            "canonical_url": CANONICAL_URL,
        }

    app.register_blueprint(pages_blueprint)
    app.register_blueprint(quiz_blueprint)
    app.register_blueprint(premium_blueprint)
    app.register_blueprint(admin_blueprint)

    @app.route("/media/<path:relative_path>")
    def media_file(relative_path: str):
        requested = (BASE_DIR / relative_path).resolve()
        if not requested.is_file():
            abort(404)
        if MEDIA_ROOT not in requested.parents:
            abort(404)
        return send_file(requested)

    return app


app = create_app()


if __name__ == "__main__":
    setup_logging()
    logger.info("Starting QuizPathshala website on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
