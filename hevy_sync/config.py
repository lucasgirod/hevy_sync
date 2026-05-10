import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = Path(os.getenv("HEVY_SYNC_CONFIG_DIR", ".")).expanduser()
HEVY_API_KEY = os.getenv("HEVY_API_KEY")

GARMIN_USERNAME = os.getenv("GARMIN_USERNAME") or os.getenv("GARMIN_EMAIL")
GARMIN_PASSWORD = os.getenv("GARMIN_PASSWORD")

legacy_tokens_file = os.getenv("GARMIN_TOKENS_FILE")
if os.getenv("GARMIN_TOKENS_DIR"):
    tokens_dir = os.getenv("GARMIN_TOKENS_DIR")
elif legacy_tokens_file:
    legacy_path = Path(legacy_tokens_file)
    tokens_dir = str(legacy_path.with_suffix("") if legacy_path.suffix else legacy_path)
else:
    tokens_dir = str(CONFIG_DIR / "garmin_tokens")

GARMIN_TOKENS_DIR = Path(tokens_dir).expanduser()
LAST_SYNC_DATE_FILE = Path(
    os.getenv("LAST_SYNC_DATE_FILE", str(CONFIG_DIR / "last_sync_date.txt"))
).expanduser()
TEMP_FIT_DIR = Path(os.getenv("TEMP_FIT_DIR", "/tmp/hevy-sync")).expanduser()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def validate_config() -> None:
    missing = []
    if not HEVY_API_KEY:
        missing.append("HEVY_API_KEY")
    if not GARMIN_USERNAME:
        missing.append("GARMIN_USERNAME")
    if not GARMIN_PASSWORD:
        missing.append("GARMIN_PASSWORD")

    if missing:
        logger.error("Missing required configuration: %s", ", ".join(missing))
        raise SystemExit(1)
