import requests
import datetime
import logging
import time
from dateutil.parser import isoparse

from .config import HEVY_API_KEY

logger = logging.getLogger(__name__)

class HevyClient:
    """
    Ein Client für die Hevy API, um Workout-Events (inkl. Änderungen) abzurufen.
    """
    def __init__(self, api_key: str):
        self.base_url = "https://api.hevyapp.com/v1"
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "api-key": self.api_key
        })
        logger.info("HevyClient initialisiert.")

    def get_workout_events_since(self, since_datetime: datetime.datetime) -> list:
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
                response = self.session.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                # Pagination
                page_count = data.get("page_count", 1)
                events = data.get("events", [])

                logger.info(f"Seite {page}/{page_count}: {len(events)} Events erhalten")

                for event in events:
                    if event.get("type") == "updated" and "workout" in event:
                        all_workouts.append(event["workout"])
                    elif event.get("type") == "deleted":
                        logger.debug(f"Ignoriere gelöschtes Workout {event.get('id')}")

                page += 1
                time.sleep(0.2)

            except requests.exceptions.RequestException as e:
                logger.error(f"Fehler beim Abrufen von Workout-Events (Seite {page}): {e}")
                break
            except ValueError as e:
                logger.error(f"Fehler beim Parsen der Antwort (Seite {page}): {e}")
                break

        logger.info(f"Insgesamt {len(all_workouts)} Workouts seit {since_datetime} erhalten.")
        return all_workouts