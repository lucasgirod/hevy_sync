import logging
import time
from datetime import datetime
from pathlib import Path

from garminconnect import Garmin

from .exercise_sets import build_exercise_sets_payload

logger = logging.getLogger(__name__)


class GarminClient:
    """
    Ein Client für den Upload von Aktivitäten zu Garmin Connect.
    """

    def __init__(self, username: str, password: str, tokens_dir: Path):
        self.username = username
        self.password = password
        self.tokens_dir = Path(tokens_dir)
        self.client = Garmin(username, password)

        self._login_or_load()

    def _login_or_load(self) -> None:
        """Versucht gespeicherte Sitzung zu laden oder meldet sich neu an."""
        self.tokens_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.client.login(str(self.tokens_dir))
            logger.info("Erfolgreich bei Garmin Connect angemeldet.")
        except Exception as e:
            logger.error(f"Login bei Garmin Connect fehlgeschlagen: {e}")
            raise

    def upload_activity_file(self, fit_file_path: str, title: str = None, workout: dict | None = None) -> bool:
        """Lädt eine FIT-Datei zu Garmin hoch."""
        fit_file = Path(fit_file_path)
        if not fit_file.exists():
            logger.error(f"FIT-Datei existiert nicht: {fit_file_path}")
            return False

        try:
            response = self.client.upload_activity(str(fit_file))
            logger.info(f"FIT-Datei '{fit_file.name}' erfolgreich hochgeladen.")
            activity_id = self._extract_activity_id(response)
            if activity_id is None and workout:
                activity_id = self._find_activity_by_start_time(workout.get("start_time"))

            if workout and activity_id:
                self._push_workout_exercise_sets(activity_id, workout)
            elif workout:
                logger.warning("Konnte keine Garmin activity_id finden; Übungsdetails wurden nicht übertragen.")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Hochladen der FIT-Datei: {e}", exc_info=True)
            return False

    def _push_workout_exercise_sets(self, activity_id: int, workout: dict) -> None:
        try:
            payload = build_exercise_sets_payload(workout, activity_id)
            if not payload["exerciseSets"]:
                logger.info("Keine Hevy-Sätze gefunden; überspringe Garmin exerciseSets.")
                return

            self.client.client.request(
                "PUT",
                "connectapi",
                f"/activity-service/activity/{activity_id}/exerciseSets",
                json=payload,
            )
            logger.info(
                "Übungsdetails mit %s Garmin exerciseSets auf Aktivität %s übertragen.",
                len(payload["exerciseSets"]),
                activity_id,
            )
        except Exception as e:
            logger.warning("FIT-Upload war erfolgreich, aber Übungsdetails konnten nicht übertragen werden: %s", e)

    def _extract_activity_id(self, response) -> int | None:
        if not isinstance(response, dict):
            return None

        for key in ("activityId", "internalId"):
            if response.get(key):
                return int(response[key])

        detailed_result = response.get("detailedImportResult", {})
        for success in detailed_result.get("successes", []):
            for key in ("internalId", "activityId"):
                if success.get(key):
                    return int(success[key])
        return None

    def _find_activity_by_start_time(self, start_time: str | None) -> int | None:
        if not start_time:
            return None

        try:
            target = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

        for wait_seconds in (2, 5, 10):
            time.sleep(wait_seconds)
            try:
                activities = self.client.get_activities(0, 10, activitytype="fitness_equipment")
            except Exception as e:
                logger.debug("Konnte Garmin-Aktivitäten nicht für activity_id-Fallback laden: %s", e)
                continue

            for activity in activities or []:
                activity_type = activity.get("activityType", {}).get("typeKey")
                if activity_type not in ("strength_training", "other"):
                    continue

                activity_start = activity.get("startTimeGMT") or activity.get("startTimeLocal")
                if not activity_start:
                    continue

                try:
                    parsed_start = datetime.fromisoformat(activity_start.replace(" ", "T")).replace(tzinfo=None)
                except ValueError:
                    continue

                if abs((parsed_start - target).total_seconds()) <= 10 * 60:
                    return int(activity["activityId"])

        return None
