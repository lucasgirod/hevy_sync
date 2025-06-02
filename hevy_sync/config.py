import os
import logging
import sys
from dotenv import dotenv_values

# Load environment variables from.env file
config = dotenv_values(".env")

# Hevy API Key
HEVY_API_KEY = config.get("HEVY_API_KEY")

# Garmin Connect Credentials
GARMIN_EMAIL = config.get("GARMIN_EMAIL")
GARMIN_PASSWORD = config.get("GARMIN_PASSWORD")

# File paths for persistence
GARMIN_TOKENS_FILE = config.get("GARMIN_TOKENS_FILE", "./garmin_tokens.json")
LAST_SYNC_DATE_FILE = config.get("LAST_SYNC_DATE_FILE", "./last_sync_date.txt")

# Logging configuration
LOG_LEVEL = config.get("LOG_LEVEL", "INFO").upper()

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
            logging.StreamHandler(sys.stdout)
        ]
)
logger = logging.getLogger(__name__)

# Validate essential configurations
if not HEVY_API_KEY:
    logger.error("HEVY_API_KEY is not set in .env file.")
    exit(1)
if not GARMIN_EMAIL or not GARMIN_PASSWORD:
    logger.error("GARMIN_EMAIL or GARMIN_PASSWORD is not set in .env file.")
    exit(1)