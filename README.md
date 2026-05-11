# hevy-sync

Synchronisiert Hevy-Workouts nach Garmin Connect als Krafttraining mit Übungen, Sätzen, Gewichten, Wiederholungen, optionaler Herzfrequenz und Kalorien-Schätzung.

Die Docker-Architektur bleibt bewusst schlank: ein Container, ein Config-Volume, ein Run. Die Sync-Funktionalität ist stark an [drkostas/hevy2garmin](https://github.com/drkostas/hevy2garmin) angelehnt und nutzt daraus adaptierte MIT-lizenzierte Konzepte und Mapping-Daten.

## Konfiguration

Die App liest Environment-Variablen und optional eine lokale `.env` Datei:

```bash
HEVY_API_KEY="..."
GARMIN_USERNAME="you@example.com"
GARMIN_PASSWORD="..."
TZ="Europe/Zurich"
```

Optionale Pfade:

```bash
HEVY_SYNC_CONFIG_DIR="./config"
GARMIN_TOKENS_DIR="./config/garmin_tokens"
SYNC_DB_FILE="./config/sync.db"
TEMP_FIT_DIR="/tmp/hevy-sync"
EXERCISE_MATCHES_FILE="./config/exercise_matches.json"
LOG_LEVEL="INFO"
```

Sync-Verhalten:

```bash
SYNC_LIMIT="10"
SYNC_FETCH_ALL="false"
SYNC_SINCE=""
SKIP_EXISTING="true"
DRY_RUN="false"
MERGE_MODE="true"
MERGE_OVERLAP_PCT="70"
MERGE_MAX_DRIFT_MIN="20"
DESCRIPTION_ENABLED="true"
HR_FUSION_ENABLED="true"
```

Profil für die Keytel-Kalorien-Schätzung:

```bash
USER_WEIGHT_KG="80"
USER_BIRTH_YEAR="1990"
USER_VO2MAX="45"
```

`GARMIN_EMAIL` und `GARMIN_TOKENS_FILE` werden aus alten Installationen weiterhin als Fallback akzeptiert. Das Compose-File zieht `ghcr.io/lucasgirod/hevy_sync:latest` bei jedem Deploy neu, damit keine alte lokale Image-Version weiterläuft.

## Wie Der Sync Läuft

1. Hevy-Workouts werden über die offizielle Hevy API gelesen.
2. Übungen werden über `exercise_matches.json` auf Garmin FIT Kategorien gemappt.
3. Wenn `MERGE_MODE=true`, sucht die App eine passende Garmin-Krafttraining-Aktivität und schreibt die Hevy-Sätze in diese Aktivität. Herzfrequenz, Training Effect und Recovery-Daten der Uhr bleiben dadurch erhalten.
4. Wenn kein passendes Garmin-Training gefunden wird, erzeugt die App eine FIT-Datei und lädt sie zu Garmin hoch.
5. Wenn `HR_FUSION_ENABLED=true`, werden Garmin-Tages-Herzfrequenzdaten in den Zeitraum des Hevy-Workouts geschnitten und ins FIT-File eingebettet.
6. Kalorien werden mit der Keytel-Formel geschätzt und in FIT-Datei/Beschreibung übernommen.
7. Synchronisierte Workouts werden in `SYNC_DB_FILE` gespeichert, standardmäßig im Docker-Volume.

## Garmin-Übungsmapping

Das Repository enthält zwei Mapping-Dateien:

- `hevy_sync/data/exercise_matches.json`: Master-Seed für Hevy-zu-Garmin-Matches, größtenteils aus `drkostas/hevy2garmin`.
- `hevy_sync/data/garmin_exercises.json`: alle Garmin-Übungen, die das verwendete FIT-Profil kennt.

Beim ersten Lauf wird `exercise_matches.json` nach `EXERCISE_MATCHES_FILE` kopiert. Im Docker-Image liegt diese Datei standardmäßig unter `/config/exercise_matches.json`. Neue automatische oder unbekannte Übungen werden nur in dieser Laufzeitdatei ergänzt. Manuelle Korrekturen dort haben Vorrang und werden bei Image-Updates nicht überschrieben.

## Lokal Ausführen

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.sample .env
hevy-sync
```

Beim ersten Garmin-Login speichert die App Tokens unter `GARMIN_TOKENS_DIR`. Danach werden die Tokens wiederverwendet.

## Docker

Image bauen:

```bash
docker build -t hevy-sync .
```

Einmalig interaktiv ausführen:

```bash
docker run --rm -it \
  -e HEVY_API_KEY="$HEVY_API_KEY" \
  -e GARMIN_USERNAME="$GARMIN_USERNAME" \
  -e GARMIN_PASSWORD="$GARMIN_PASSWORD" \
  -v "<instance-name>-config:/config" \
  ghcr.io/lucasgirod/hevy_sync:latest
```

## Docker Compose

Dieses Repository enthält ein `docker-compose.yaml` für einen direkt startbaren Container:

```bash
docker compose -f docker-compose.yaml run --rm hevy-sync
```

Das Compose-Volume speichert Garmin-Tokens, SQLite-State, HR-Cache und das korrigierbare `exercise_matches.json`. Der Volume-Name wird von Docker Compose pro Projekt/Stack namespaced, sodass mehrere Instanzen auf demselben Host laufen können.

Für lokale Tests direkt aus dem Arbeitsverzeichnis:

```bash
docker build -t hevy-sync:local .
docker run --rm -it --env-file .env -e DRY_RUN=true -v hevy-sync-test:/config hevy-sync:local
```

Hinweis: `docker run --env-file` interpretiert Anführungszeichen anders als Docker Compose. Wenn deine `.env` Werte in Quotes enthält, ist Compose robuster.

## Attribution

Teile der Sync-Funktionalität und die große Übungsmapping-Tabelle sind aus [drkostas/hevy2garmin](https://github.com/drkostas/hevy2garmin) adaptiert. Siehe [NOTICE.md](NOTICE.md).
