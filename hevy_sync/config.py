import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return value


def _env_bool(name: str, default: str = "false") -> bool:
    return (_env(name, default) or "").lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: str) -> int:
    return int(_env(name, default) or default)


def _env_float(name: str, default: str) -> float:
    return float(_env(name, default) or default)


def _env_path(name: str, default: str) -> Path:
    return Path(_env(name, default) or default).expanduser()


CONFIG_DIR = _env_path("HEVY_SYNC_CONFIG_DIR", ".")
HEVY_API_KEY = _env("HEVY_API_KEY")

GARMIN_USERNAME = _env("GARMIN_USERNAME")
GARMIN_PASSWORD = _env("GARMIN_PASSWORD")

GARMIN_TOKENS_DIR = _env_path("GARMIN_TOKENS_DIR", str(CONFIG_DIR / "garmin_tokens"))
TEMP_FIT_DIR = _env_path("TEMP_FIT_DIR", "/tmp/hevy-sync")
EXERCISE_MATCHES_FILE = Path(
    _env("EXERCISE_MATCHES_FILE", str(CONFIG_DIR / "exercise_matches.json"))
).expanduser()
SYNC_DB_FILE = _env_path("SYNC_DB_FILE", str(CONFIG_DIR / "sync.db"))

SYNC_LIMIT = _env_int("SYNC_LIMIT", "10")
SYNC_FETCH_ALL = _env_bool("SYNC_FETCH_ALL")
SYNC_SINCE = _env("SYNC_SINCE")
SKIP_EXISTING = _env_bool("SKIP_EXISTING", "true")
DRY_RUN = _env_bool("DRY_RUN")

MERGE_MODE = _env_bool("MERGE_MODE", "true")
MERGE_OVERLAP_PCT = _env_float("MERGE_OVERLAP_PCT", "70")
MERGE_MAX_DRIFT_MIN = _env_int("MERGE_MAX_DRIFT_MIN", "20")
DESCRIPTION_ENABLED = _env_bool("DESCRIPTION_ENABLED", "true")
HR_FUSION_ENABLED = _env_bool("HR_FUSION_ENABLED", "true")

USER_WEIGHT_KG = _env_float("USER_WEIGHT_KG", "80")
USER_BIRTH_YEAR = _env_int("USER_BIRTH_YEAR", "1990")
USER_VO2MAX = _env_float("USER_VO2MAX", "45")
WORKING_SET_SECONDS = _env_int("WORKING_SET_SECONDS", "40")
WARMUP_SET_SECONDS = _env_int("WARMUP_SET_SECONDS", "25")
REST_BETWEEN_SETS_SECONDS = _env_int("REST_BETWEEN_SETS_SECONDS", "75")
REST_BETWEEN_EXERCISES_SECONDS = _env_int("REST_BETWEEN_EXERCISES_SECONDS", "120")

LOG_LEVEL = (_env("LOG_LEVEL", "INFO") or "INFO").upper()

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
