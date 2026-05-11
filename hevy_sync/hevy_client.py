import requests
import logging
import time
from datetime import datetime


logger = logging.getLogger(__name__)


class HevyClient:
    """
    Ein Client für die Hevy API, um Workout-Events (inkl. Änderungen) abzurufen.
    """
    def __init__(self, api_key: str):
        self.base_url = "https://api.hevyapp.com/v1"
        self.api_key = api_key
        self._exercise_template_cache = {}
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "api-key": self.api_key
        })
        logger.info("HevyClient initialisiert.")

    def get_workout_events_since(self, since_datetime: datetime) -> list:
        """
        Holt alle Workout-Events seit dem gegebenen Zeitpunkt.

        Args:
            since_datetime (datetime.datetime): Zeitpunkt, ab dem neue/aktualisierte Workouts berücksichtigt werden sollen.

        Returns:
            list: Liste der Workouts (nicht Events), die seit diesem Zeitpunkt geändert wurden.
        """
        all_workouts = []
        page = 1
        page_count = None

        while page_count is None or page <= page_count:
            url = f"{self.base_url}/workouts/events"
            params = {
                "page": page,
                "pageSize": 10,
                "since": since_datetime.isoformat()
            }

            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Pagination
                page_count = data.get("page_count", 1)
                events = data.get("events", [])

                logger.info(f"Seite {page}/{page_count}: {len(events)} Events erhalten")

                for event in events:
                    if event.get("type") == "updated" and "workout" in event:
                        workout = event["workout"]
                        self._enrich_exercise_template_titles(workout)
                        all_workouts.append(workout)
                    elif event.get("type") == "deleted":
                        logger.debug(f"Ignoriere gelöschtes Workout {event.get('id')}")
                    else:
                        logger.warning("Ignoriere unbekanntes Workout-Event: %s", event.get("type"))

                page += 1
                time.sleep(0.2)

            except requests.exceptions.RequestException as e:
                logger.error(f"Fehler beim Abrufen von Workout-Events (Seite {page}): {e}")
                raise
            except ValueError as e:
                logger.error(f"Fehler beim Parsen der Antwort (Seite {page}): {e}")
                raise

        logger.info(f"Insgesamt {len(all_workouts)} Workouts seit {since_datetime} erhalten.")
        return all_workouts

    def get_workout_count(self) -> int:
        response = self.session.get(f"{self.base_url}/workouts/count", timeout=30)
        response.raise_for_status()
        return int(response.json()["workout_count"])

    def get_workouts(self, page: int = 1, page_size: int = 10) -> dict:
        response = self.session.get(
            f"{self.base_url}/workouts",
            params={"page": page, "pageSize": page_size},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        for workout in data.get("workouts", []):
            self._enrich_exercise_template_titles(workout)
        return data

    def get_recent_workouts(self, limit: int | None = None, since: str | None = None, fetch_all: bool = False) -> list[dict]:
        if not fetch_all and limit and limit <= 10:
            data = self.get_workouts(page=1, page_size=limit)
            return data.get("workouts", [])[:limit]

        workouts = []
        page = 1
        while True:
            page_size = min(10, limit - len(workouts)) if limit else 10
            if page_size <= 0:
                break
            data = self.get_workouts(page=page, page_size=page_size)
            page_workouts = data.get("workouts", [])
            if not page_workouts:
                break
            for workout in page_workouts:
                start = workout.get("start_time") or workout.get("startTime", "")
                if since and start < since:
                    logger.info("Datumsgrenze erreicht (%s), stoppe Hevy-Fetch.", since)
                    return workouts
                workouts.append(workout)
                if limit and len(workouts) >= limit:
                    return workouts
            logger.info("Bisher %s Hevy-Workouts geladen.", len(workouts))
            if page >= data.get("page_count", page):
                break
            page += 1
        return workouts

    def _enrich_exercise_template_titles(self, workout: dict) -> None:
        for exercise in workout.get("exercises", []):
            template_id = exercise.get("exercise_template_id")
            if not template_id:
                continue

            title = self._get_exercise_template_title(template_id)
            if title:
                exercise["exercise_template_title"] = title

    def _get_exercise_template_title(self, template_id: str) -> str | None:
        if template_id in self._exercise_template_cache:
            return self._exercise_template_cache[template_id]

        try:
            response = self.session.get(f"{self.base_url}/exercise_templates/{template_id}", timeout=30)
            response.raise_for_status()
            title = response.json().get("title")
            self._exercise_template_cache[template_id] = title
            return title
        except requests.exceptions.RequestException as e:
            logger.debug("Konnte Hevy Exercise Template %s nicht laden: %s", template_id, e)
            self._exercise_template_cache[template_id] = None
            return None
