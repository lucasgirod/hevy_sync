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
EXERCISE_MATCHES_FILE = Path(
    os.getenv("EXERCISE_MATCHES_FILE", str(CONFIG_DIR / "exercise_matches.json"))
).expanduser()
SYNC_DB_FILE = Path(os.getenv("SYNC_DB_FILE", str(CONFIG_DIR / "sync.db"))).expanduser()

SYNC_LIMIT = int(os.getenv("SYNC_LIMIT", "10"))
SYNC_FETCH_ALL = os.getenv("SYNC_FETCH_ALL", "false").lower() in ("1", "true", "yes", "on")
SYNC_SINCE = os.getenv("SYNC_SINCE")
SKIP_EXISTING = os.getenv("SKIP_EXISTING", "true").lower() in ("1", "true", "yes", "on")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() in ("1", "true", "yes", "on")

MERGE_MODE = os.getenv("MERGE_MODE", "true").lower() in ("1", "true", "yes", "on")
MERGE_OVERLAP_PCT = float(os.getenv("MERGE_OVERLAP_PCT", "70"))
MERGE_MAX_DRIFT_MIN = int(os.getenv("MERGE_MAX_DRIFT_MIN", "20"))
DESCRIPTION_ENABLED = os.getenv("DESCRIPTION_ENABLED", "true").lower() in ("1", "true", "yes", "on")
HR_FUSION_ENABLED = os.getenv("HR_FUSION_ENABLED", "true").lower() in ("1", "true", "yes", "on")

USER_WEIGHT_KG = float(os.getenv("USER_WEIGHT_KG", "80"))
USER_BIRTH_YEAR = int(os.getenv("USER_BIRTH_YEAR", "1990"))
USER_VO2MAX = float(os.getenv("USER_VO2MAX", "45"))
WORKING_SET_SECONDS = int(os.getenv("WORKING_SET_SECONDS", "40"))
WARMUP_SET_SECONDS = int(os.getenv("WARMUP_SET_SECONDS", "25"))
REST_BETWEEN_SETS_SECONDS = int(os.getenv("REST_BETWEEN_SETS_SECONDS", "75"))
REST_BETWEEN_EXERCISES_SECONDS = int(os.getenv("REST_BETWEEN_EXERCISES_SECONDS", "120"))

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


def load_runtime_config() -> dict:
    """Return runtime config in the shape used by the adapted hevy2garmin modules."""
    return {
        "hevy_api_key": HEVY_API_KEY,
        "garmin_email": GARMIN_USERNAME,
        "garmin_password": GARMIN_PASSWORD,
        "garmin_token_dir": str(GARMIN_TOKENS_DIR),
        "sync": {
            "default_limit": SYNC_LIMIT,
            "skip_existing": SKIP_EXISTING,
            "dry_run": DRY_RUN,
        },
        "merge_mode": MERGE_MODE,
        "merge_overlap_pct": MERGE_OVERLAP_PCT,
        "merge_max_drift_min": MERGE_MAX_DRIFT_MIN,
        "description_enabled": DESCRIPTION_ENABLED,
        "hr_fusion": {
            "enabled": HR_FUSION_ENABLED,
        },
        "user_profile": {
            "weight_kg": USER_WEIGHT_KG,
            "birth_year": USER_BIRTH_YEAR,
            "vo2max": USER_VO2MAX,
        },
        "timing": {
            "working_set_seconds": WORKING_SET_SECONDS,
            "warmup_set_seconds": WARMUP_SET_SECONDS,
            "rest_between_sets_seconds": REST_BETWEEN_SETS_SECONDS,
            "rest_between_exercises_seconds": REST_BETWEEN_EXERCISES_SECONDS,
        },
    }
