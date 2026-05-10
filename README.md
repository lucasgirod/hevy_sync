# hevy-sync

Synchronisiert Hevy-Workouts als FIT-Aktivitäten nach Garmin Connect.

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
LAST_SYNC_DATE_FILE="./config/last_sync_date.txt"
TEMP_FIT_DIR="/tmp/hevy-sync"
LOG_LEVEL="INFO"
```

`GARMIN_EMAIL` und `GARMIN_TOKENS_FILE` werden aus alten Installationen weiterhin als Fallback akzeptiert.

## Lokal ausfuehren

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.sample .env
hevy-sync
```

Beim ersten Lauf meldet sich die App bei Garmin an und speichert Tokens unter `GARMIN_TOKENS_DIR`. Der naechste Hevy-Zeitpunkt wird in `LAST_SYNC_DATE_FILE` persistiert.

## Docker

Image bauen:

```bash
docker build -t hevy-sync .
```

Einmalig interaktiv ausfuehren:

```bash
docker run --rm -it \
  -e HEVY_API_KEY="$HEVY_API_KEY" \
  -e GARMIN_USERNAME="$GARMIN_USERNAME" \
  -e GARMIN_PASSWORD="$GARMIN_PASSWORD" \
  -v hevy-sync-lucas:/config \
  hevy-sync
```

## Docker Compose

Dieses Repository enthaelt ein `compose.yaml`, das zum bestehenden `withings-sync` Muster passt:

```bash
docker volume create hevy-sync-lucas
docker compose run --rm hevy-sync
```

Wenn du das konfigurierte `entrypoint: "sh /config/entrypoint.sh"` nutzt, muss im Volume `/config/entrypoint.sh` existieren. Beispiel:

```sh
#!/bin/sh
hevy-sync
```

## Release

GitHub Actions baut und veroeffentlicht das Docker Image nach `ghcr.io/lucasgirod/hevy_sync` bei Pushes auf `main`, Release-Tags `v*.*.*`, manuellen Runs und dem 5-Tage-Schedule. Pull Requests bauen das Image ohne Push.
