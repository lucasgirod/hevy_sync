import logging
from pathlib import Path

from garminconnect import Garmin

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

    def upload_activity_file(self, fit_file_path: str, title: str = None) -> bool:
        """Lädt eine FIT-Datei zu Garmin hoch."""
        fit_file = Path(fit_file_path)
        if not fit_file.exists():
            logger.error(f"FIT-Datei existiert nicht: {fit_file_path}")
            return False

        try:
            self.client.upload_activity(str(fit_file))
            logger.info(f"FIT-Datei '{fit_file.name}' erfolgreich hochgeladen.")
            return True
        except Exception as e:
            logger.error(f"Fehler beim Hochladen der FIT-Datei: {e}", exc_info=True)
            return False
