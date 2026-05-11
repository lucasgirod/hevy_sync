"""Container entrypoint for Hevy -> Garmin sync."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from .config import (
    DESCRIPTION_ENABLED,
    DRY_RUN,
    GARMIN_PASSWORD,
    GARMIN_TOKENS_DIR,
    GARMIN_USERNAME,
    HEVY_API_KEY,
    HR_FUSION_ENABLED,
    MERGE_MAX_DRIFT_MIN,
    MERGE_MODE,
    MERGE_OVERLAP_PCT,
    SYNC_DB_FILE,
    SYNC_FETCH_ALL,
    SYNC_LIMIT,
    SYNC_SINCE,
    TEMP_FIT_DIR,
    validate_config,
)
from .fit import generate_fit
from .garmin import (
    find_matching_garmin_activity,
    find_activity_by_start_time,
    generate_description,
    get_client,
    rename_activity,
    set_description,
    upload_fit,
)
from .hevy_client import HevyClient
from .hr import get_workout_hr_samples
from .mapper import ensure_exercise_matches_file, lookup_exercise
from .merge import attempt_merge, reset_circuit_breaker
from .state import SQLiteState

logger = logging.getLogger(__name__)


def main() -> int:
    logger.info("Starting hevy-sync container run...")
    validate_config()
    ensure_exercise_matches_file()
    TEMP_FIT_DIR.mkdir(parents=True, exist_ok=True)

    state = SQLiteState(SYNC_DB_FILE)
    hevy = HevyClient(api_key=HEVY_API_KEY)

    try:
        total_count = hevy.get_workout_count()
        logger.info("Hevy meldet %s Workouts insgesamt.", total_count)
        limit = None if SYNC_FETCH_ALL else SYNC_LIMIT
        workouts = hevy.get_recent_workouts(limit=limit, since=SYNC_SINCE, fetch_all=SYNC_FETCH_ALL)
    except Exception as exc:
        logger.error("Hevy-Workouts konnten nicht geladen werden: %s", exc)
        return 1

    logger.info("%s Hevy-Workouts werden geprüft.", len(workouts))
    if not workouts:
        state.record_sync_log(synced=0, skipped=0, failed=0, trigger="container")
        return 0

    for workout in workouts:
        for exercise in workout.get("exercises", []):
            cat, _, _ = lookup_exercise(exercise)
            if cat == 65534:
                logger.warning("Nicht gemappte Übung: %s", exercise.get("title") or exercise.get("name"))

    garmin_client = None
    if DRY_RUN:
        logger.info("DRY_RUN aktiv: Garmin wird nur lesend verwendet, es werden keine Änderungen geschrieben.")

    try:
        logger.info("Authentifiziere bei Garmin Connect...")
        garmin_client = get_client(GARMIN_USERNAME, GARMIN_PASSWORD, str(GARMIN_TOKENS_DIR))
    except Exception as exc:
        if DRY_RUN:
            logger.warning("Garmin-Login im DRY_RUN fehlgeschlagen; fahre ohne HR/Merge-Test fort: %s", exc)
        else:
            logger.error("Garmin-Login fehlgeschlagen: %s", exc)
            return 1

    stats = {
        "synced": 0,
        "skipped": 0,
        "failed": 0,
        "merged": 0,
        "uploaded": 0,
        "merge_fallback": 0,
    }

    if MERGE_MODE:
        reset_circuit_breaker()
        logger.info("Merge-Modus aktiv: passende Garmin-Krafttrainings werden mit Hevy-Sätzen ergänzt.")

    for workout in workouts:
        workout_id = workout.get("id", "unknown")
        title = workout.get("title", "Workout")
        start_time = workout.get("start_time") or workout.get("startTime")

        if state.is_synced(workout_id):
            logger.info("Überspringe bereits synchronisiertes Workout: %s", title)
            stats["skipped"] += 1
            continue

        logger.info("Synchronisiere: %s (%s)", title, workout_id)
        try:
            if MERGE_MODE and garmin_client and not DRY_RUN:
                merge_result = attempt_merge(
                    garmin_client,
                    workout,
                    state,
                    overlap_threshold=MERGE_OVERLAP_PCT / 100.0,
                    max_drift_minutes=MERGE_MAX_DRIFT_MIN,
                )
                if merge_result.merged:
                    state.mark_synced(
                        hevy_id=workout_id,
                        garmin_activity_id=str(merge_result.activity_id),
                        title=title,
                        hevy_updated_at=workout.get("updated_at"),
                        sync_method="merge",
                    )
                    stats["synced"] += 1
                    stats["merged"] += 1
                    logger.info("Workout in bestehende Garmin-Aktivität %s übernommen.", merge_result.activity_id)
                    continue

                stats["merge_fallback"] += 1
                logger.info("Merge-Fallback für %s: %s", title, merge_result.fallback_reason)
            elif MERGE_MODE and garmin_client and DRY_RUN:
                match = find_matching_garmin_activity(
                    garmin_client,
                    workout,
                    overlap_threshold=MERGE_OVERLAP_PCT / 100.0,
                    max_drift_minutes=MERGE_MAX_DRIFT_MIN,
                )
                if match:
                    logger.info("DRY_RUN: würde in Garmin-Aktivität %s mergen.", match.get("activityId"))
                else:
                    logger.info("DRY_RUN: keine passende Garmin-Aktivität für Merge gefunden.")

            hr_samples = get_workout_hr_samples(garmin_client, workout, state) if HR_FUSION_ENABLED and garmin_client else []
            if HR_FUSION_ENABLED:
                logger.info("%s Garmin-HR-Samples für '%s' gefunden.", len(hr_samples), title)
            with tempfile.TemporaryDirectory(dir=TEMP_FIT_DIR) as tmp:
                fit_path = str(Path(tmp) / f"{workout_id}.fit")
                result = generate_fit(workout, hr_samples=hr_samples, output_path=fit_path)
                logger.info(
                    "FIT erzeugt: %s Übungen, %s Sätze, %s HR-Samples, %s kcal.",
                    result["exercises"],
                    result["total_sets"],
                    result["hr_samples"],
                    result["calories"],
                )

                if DRY_RUN:
                    logger.info("DRY_RUN: FIT-Datei würde hochgeladen: %s", fit_path)
                    activity_id = None
                else:
                    existing_id = find_activity_by_start_time(garmin_client, start_time) if start_time else None
                    if existing_id:
                        activity_id = existing_id
                        logger.info("Garmin-Aktivität existiert bereits (%s), Upload wird übersprungen.", activity_id)
                    else:
                        upload_result = upload_fit(garmin_client, fit_path, workout_start=start_time)
                        activity_id = upload_result.get("activity_id")

                if activity_id and garmin_client:
                    rename_activity(garmin_client, activity_id, title)
                    if DESCRIPTION_ENABLED:
                        set_description(
                            garmin_client,
                            activity_id,
                            generate_description(
                                workout,
                                calories=result.get("calories"),
                                avg_hr=result.get("avg_hr"),
                            ),
                        )

                if not DRY_RUN:
                    state.mark_synced(
                        hevy_id=workout_id,
                        garmin_activity_id=str(activity_id) if activity_id else None,
                        title=title,
                        calories=result.get("calories"),
                        avg_hr=result.get("avg_hr"),
                        hevy_updated_at=workout.get("updated_at"),
                        sync_method="upload_fallback" if MERGE_MODE else "upload",
                    )
                stats["synced"] += 1
                stats["uploaded"] += 1
                logger.info("Workout synchronisiert: %s -> Garmin %s", title, activity_id)

        except Exception as exc:
            stats["failed"] += 1
            logger.error("Workout '%s' konnte nicht synchronisiert werden: %s", title, exc, exc_info=True)

    state.record_sync_log(
        synced=stats["synced"],
        skipped=stats["skipped"],
        failed=stats["failed"],
        trigger="github-actions" if os.environ.get("GITHUB_ACTIONS") else "container",
    )
    logger.info(
        "Sync fertig: %s synced, %s merged, %s uploaded, %s skipped, %s failed.",
        stats["synced"],
        stats["merged"],
        stats["uploaded"],
        stats["skipped"],
        stats["failed"],
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
