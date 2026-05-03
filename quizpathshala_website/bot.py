from app import app
from config import PORT
from utils.logging_utils import get_logger, setup_logging


logger = get_logger(__name__)


def main() -> None:
    setup_logging()
    logger.info("Legacy launcher redirecting to website app on port %s", PORT)
    app.run(host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
