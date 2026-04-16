import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(".env")

if not load_dotenv(ENV_FILE):
    # Missing file is OK: secrets may come from the parent environment instead.
    pass

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

if ENV_FILE.is_file():
    logger.info("Loaded environment from %s", ENV_FILE.resolve())
else:
    logger.warning(
        "No %s file — expecting required variables in the process environment",
        ENV_FILE,
    )

REQUIRED_ENV = {
    "TELEGRAM_BOT_TOKEN": "Telegram bot token from @BotFather",
    "DOWNLOADS_DIR_PATH": "Directory for incoming audio before beets import",
    "CHECKPOINTS_DIR_PATH": "Directory for checkpoint state",
    "WHITELIST_CHAT_IDS": (
        "Comma-separated integer chat ids, no spaces (e.g. -100111,-100222)"
    ),
}

missing = [key for key in REQUIRED_ENV if not os.getenv(key, "").strip()]
if missing:
    for key in missing:
        logger.error(
            "Missing or empty required environment variable %s (%s). "
            "Set it in %s or export it in the environment.",
            key,
            REQUIRED_ENV[key],
            ENV_FILE,
        )
    sys.exit(1)

downloads = Path(os.environ["DOWNLOADS_DIR_PATH"])
checkpoints = Path(os.environ["CHECKPOINTS_DIR_PATH"])
token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_ids = set(map(int, os.environ["WHITELIST_CHAT_IDS"].split(",")))

logger.debug("Whitelisting the following chat ids: %s", chat_ids)
