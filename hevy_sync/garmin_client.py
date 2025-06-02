import os
import io
import logging
from garth import Client, http

# Optional: Setze User-Agent, um Upload-Probleme zu vermeiden
http.USER_AGENT = {"User-Agent": "GCM-iOS-5.7.2.1"}

logger = logging.getLogger(__name__)

class GarminClient:
    """
    Ein Client für den Upload von Aktivitäten zu Garmin Connect über die `garth`-Bibliothek.
    """
    def __init__(self, email: str, password: str, tokens_file: str):
        self.email = email
        self.password = password
        self.tokens_file = tokens_file
        self.client = Client()

        self._login_or_load()

    def _login_or_load(self):
        """Versucht gespeicherte Sitzung zu laden oder meldet sich neu an."""
        if os.path.exists(self.tokens_file):
            try:
                self.client.load(self.tokens_file)
                logger.info("Garmin-Sitzung aus Datei geladen.")
                return
            except Exception as e:
                logger.warning(f"Konnte gespeicherte Sitzung nicht laden: {e}")

        try:
            self.client.login(self.email, self.password)
            self.client.dump(self.tokens_file)
            logger.info("Erfolgreich bei Garmin Connect angemeldet.")
        except Exception as e:
            logger.error(f"Login bei Garmin Connect fehlgeschlagen: {e}")
            raise

    def upload_activity_file(self, fit_file_path: str, title: str = None) -> bool:
        """Lädt eine FIT-Datei zu Garmin hoch."""
        if not os.path.exists(fit_file_path):
            logger.error(f"FIT-Datei existiert nicht: {fit_file_path}")
            return False

        try:
            with open(fit_file_path, 'rb') as f:
                buffer = io.BytesIO(f.read())
                buffer.name = os.path.basename(fit_file_path)
                self.client.upload(buffer)
                logger.info(f"✅ FIT-Datei '{buffer.name}' erfolgreich hochgeladen.")
                return True
        except Exception as e:
            logger.error(f"❌ Fehler beim Hochladen der FIT-Datei: {e}", exc_info=True)
            return False
