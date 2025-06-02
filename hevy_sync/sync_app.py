import logging
import os
import json
from datetime import datetime, timedelta, timezone

from .config import (
    HEVY_API_KEY, GARMIN_EMAIL, GARMIN_PASSWORD,
    GARMIN_TOKENS_FILE, LAST_SYNC_DATE_FILE, logger
)
from .hevy_client import HevyClient
from .garmin_client import GarminClient
from .fit_generator import FitGenerator

def get_last_sync_date() -> datetime:
    """Reads the last synchronization date from a file."""
    if os.path.exists(LAST_SYNC_DATE_FILE):
        with open(LAST_SYNC_DATE_FILE, 'r') as f:
            date_str = f.read().strip()
            if date_str:
                try:
                    return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
                except ValueError:
                    logger.warning(f"Invalid date format in {LAST_SYNC_DATE_FILE}. Starting from scratch.")
    fallback_date = datetime.now(timezone.utc) - timedelta(days=30)
    logger.info(f"No last sync date found. Using default (30 days ago): {fallback_date.isoformat()}")
    return fallback_date

def set_last_sync_date(sync_date: datetime):
    """Writes the last synchronization date to a file."""
    with open(LAST_SYNC_DATE_FILE, 'w') as f:
        f.write(sync_date.isoformat())

def main():
    logger.info("Starting hevy-to-garmin-sync process...")

    # Initialize clients
    hevy_client = HevyClient(api_key=HEVY_API_KEY)
    garmin_client = GarminClient(email=GARMIN_EMAIL, password=GARMIN_PASSWORD, tokens_file=GARMIN_TOKENS_FILE)
    fit_generator = FitGenerator()

    last_sync_date = get_last_sync_date()
    current_time = datetime.now(timezone.utc)

    try:
        workouts_to_sync = hevy_client.get_workout_events_since(last_sync_date)
        logger.info(f"Found {len(workouts_to_sync)} workouts from Hevy since {last_sync_date.isoformat()}.")
        logger.debug(f"Workouts to sync:\n{json.dumps(workouts_to_sync, indent=2, ensure_ascii=False)}")
    except Exception as e:
        logger.error(f"Failed to fetch workouts from Hevy: {e}")
        return

    if not workouts_to_sync:
        logger.info("No new workouts to sync from Hevy.")
        set_last_sync_date(current_time)
        return

    successful_uploads = 0
    latest_workout_time = last_sync_date

    for workout in workouts_to_sync:
        workout_start_time_str = workout.get('start_time')
        if not workout_start_time_str:
            logger.warning(f"Workout '{workout.get('title')}' has no start_time. Skipping.")
            continue

        try:
            workout_start_time = datetime.fromisoformat(workout_start_time_str.replace('Z', '+00:00'))
        except ValueError:
            logger.warning(f"Could not parse start_time for workout: {workout.get('title')} ({workout_start_time_str}). Skipping.")
            continue

        if workout_start_time <= last_sync_date:
            logger.info(f"Skipping already synced workout: {workout.get('title')} ({workout_start_time.isoformat()})")
            continue

        if workout_start_time > latest_workout_time:
            latest_workout_time = workout_start_time

        try:
            fit_file_path = fit_generator.generate_strength_activity_fit(workout)
            if garmin_client.upload_activity_file(fit_file_path, workout.get('title')):
                logger.info(f"✅ Synced workout '{workout.get('title')}' to Garmin Connect.")
                successful_uploads += 1
            else:
                logger.error(f"❌ Failed to sync workout '{workout.get('title')}' to Garmin Connect.")
        except Exception as e:
                logger.error(f"⚠️ Error processing/uploading workout '{workout.get('title')}': {e}", exc_info=True)
        finally:
            if 'fit_file_path' in locals() and os.path.exists(fit_file_path):
                os.remove(fit_file_path)
                logger.debug(f"Removed temporary FIT file: {fit_file_path}")

    # Update last sync time with a small buffer
    next_sync_time = latest_workout_time + timedelta(seconds=1)
    set_last_sync_date(next_sync_time)

    logger.info(f"Synchronization complete. Successfully uploaded {successful_uploads} workouts.")
    logger.info(f"Next sync will start from: {next_sync_time.isoformat()}")

if __name__ == "__main__":
    main()
