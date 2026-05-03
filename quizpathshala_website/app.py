from webhook_server import app

from config import PORT
from utils.logging_utils import get_logger, setup_logging


logger = get_logger(__name__)


if __name__ == "__main__":
    setup_logging()
    logger.info("Starting QuizPathshala public site on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)
