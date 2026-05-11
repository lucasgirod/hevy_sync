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
HEVY_SYNC_DOMAIN="hevy-sync.example.com"
LETSENCRYPT_EMAIL="you@example.com"
CLOUDFLARE_API_TOKEN="..."
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
SYNC_CRON="0 9,20 * * *"
RUN_ON_START="false"
DRY_RUN="false"
MERGE_MODE="true"
MERGE_OVERLAP_PCT="70"
MERGE_MAX_DRIFT_MIN="20"
DESCRIPTION_ENABLED="true"
HR_FUSION_ENABLED="true"
```

`SYNC_CRON` nutzt die Zeitzone aus `TZ`. Der Standard `0 9,20 * * *` führt den Sync täglich um 09:00 und 20:00 aus.

Webhook:

```bash
WEBHOOK_PATH="/webhook/hevy"
WEBHOOK_SECRET="change-me"
```

Wenn `WEBHOOK_SECRET` gesetzt ist, akzeptiert der Webhook entweder `Authorization: Bearer <secret>`, einen direkten Secret-Header (`X-Webhook-Secret`, `X-Hevy-Webhook-Secret`, `X-Hevy-Secret`) oder eine HMAC-SHA256-Signatur (`X-Hevy-Signature`, `X-Hub-Signature-256`, `X-Signature`) über den Request-Body.

Profil-Fallbacks für die Keytel-Kalorien-Schätzung:

```bash
USER_WEIGHT_KG="80"
USER_BIRTH_YEAR="1990"
USER_VO2MAX="45"
```

Diese Werte werden normalerweise aus Garmin Connect gelesen. Die Env-Werte werden nur verwendet, wenn Garmin einzelne Profilwerte nicht liefert oder der Garmin-Login im Dry-Run nicht verfügbar ist.

Das Compose-File zieht `ghcr.io/lucasgirod/hevy_sync:latest` und `caddybuilds/caddy-cloudflare:latest` bei jedem Deploy neu, damit keine alte lokale Image-Version weiterläuft.

## Wie Der Sync Läuft

1. Der Container läuft als dauerhafter Dienst mit internem Cron-Scheduler und HTTPS-Webhook.
2. Der Cron triggert standardmäßig täglich um 09:00 und 20:00.
3. Hevy kann zusätzlich einen Webhook auf `https://<HEVY_SYNC_DOMAIN><WEBHOOK_PATH>` auslösen; der Webhook antwortet sofort und queued einen Sync im Hintergrund.
4. Hevy-Workouts werden über die offizielle Hevy API gelesen.
5. Übungen werden über `exercise_matches.json` auf Garmin FIT Kategorien gemappt.
6. Wenn `MERGE_MODE=true`, sucht die App eine passende Garmin-Krafttraining-Aktivität und schreibt die Hevy-Sätze in diese Aktivität. Herzfrequenz, Training Effect und Recovery-Daten der Uhr bleiben dadurch erhalten.
7. Wenn kein passendes Garmin-Training gefunden wird, erzeugt die App eine FIT-Datei und lädt sie zu Garmin hoch.
8. Wenn `HR_FUSION_ENABLED=true`, werden Garmin-Tages-Herzfrequenzdaten in den Zeitraum des Hevy-Workouts geschnitten und ins FIT-File eingebettet.
9. Gewicht, Jahrgang und VO2Max werden aus Garmin Connect gelesen; fehlende Werte fallen auf die optionalen `USER_*` Env-Werte zurück.
10. Kalorien werden mit der Keytel-Formel geschätzt und in FIT-Datei/Beschreibung übernommen.
11. Synchronisierte Workouts werden in `SYNC_DB_FILE` gespeichert, standardmäßig im Docker-Volume.

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

App-Image bauen:

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

Dieses Repository enthält ein `docker-compose.yaml` für einen direkt startbaren Dienst-Stack:

```bash
docker compose -f docker-compose.yaml up -d
```

Der Stack besteht aus:

- `hevy-sync`: dauerhafter App-Service mit Cron und Webhook auf Port 8000 im Docker-Netz.
- `caddy`: HTTPS-Reverse-Proxy auf Port 443 mit Let’s Encrypt und Cloudflare-DNS-Challenge über `caddybuilds/caddy-cloudflare:latest`.

Das Compose-Volume `config` speichert Garmin-Tokens, SQLite-State, HR-Cache und das korrigierbare `exercise_matches.json`. `caddy_data` und `caddy_config` speichern Zertifikate und Caddy-State. Die `Caddyfile` aus dem Repository wird in den Caddy-Container gemountet. Die Volume-Namen werden von Docker Compose pro Projekt/Stack namespaced, sodass mehrere Instanzen auf demselben Host laufen können.

Für Let’s Encrypt per Cloudflare muss `HEVY_SYNC_DOMAIN` auf den Host zeigen und `CLOUDFLARE_API_TOKEN` mindestens `Zone.Zone:Read` und `Zone.DNS:Edit` für die Zone besitzen.

Webhook-URL für Hevy:

```text
https://<HEVY_SYNC_DOMAIN>/webhook/hevy
```

Healthcheck:

```bash
curl https://<HEVY_SYNC_DOMAIN>/health
```

## Hevy Webhook Einrichten

1. Stelle sicher, dass der Stack läuft und Caddy ein Zertifikat erhalten hat:

```bash
docker compose -f docker-compose.yaml up -d
curl https://<HEVY_SYNC_DOMAIN>/health
```

Der Healthcheck sollte ungefähr so antworten:

```json
{"status":"ok","running":false,"webhook_path":"/webhook/hevy"}
```

2. Öffne in Hevy die Developer-/API-Einstellungen und erstelle einen neuen Webhook.

3. Trage als Webhook-URL ein:

```text
https://<HEVY_SYNC_DOMAIN>/webhook/hevy
```

Wenn du `WEBHOOK_PATH` geändert hast, nutze stattdessen diesen Pfad.

4. Hinterlege das Secret aus deiner `.env` (`WEBHOOK_SECRET`). Falls Hevy eine Header-Konfiguration erlaubt, verwende eine dieser Varianten:

```text
Authorization: Bearer <WEBHOOK_SECRET>
```

oder:

```text
X-Webhook-Secret: <WEBHOOK_SECRET>
```

Wenn Hevy stattdessen eine HMAC-Signatur über den Body sendet, werden `X-Hevy-Signature`, `X-Hub-Signature-256` und `X-Signature` akzeptiert. Das Format darf `sha256=<hex>` oder nur `<hex>` sein.

5. Aktiviere Events für erstellte oder aktualisierte Workouts. Der konkrete Event-Name ist für diese App nicht kritisch: jeder gültig signierte POST auf den Webhook queued einen Sync. Gelöschte Workouts werden aktuell nicht aktiv aus Garmin entfernt.

6. Teste den Webhook in Hevy. In den Container-Logs solltest du eine `202`-Antwort und danach einen Sync-Run sehen:

```bash
docker compose -f docker-compose.yaml logs -f hevy-sync
```

Erwartete Log-Zeilen:

```text
"POST /webhook/hevy HTTP/1.1" 202
Starting hevy-sync container run...
```

Wenn Hevy `401` erhält, passt das Secret nicht oder wird nicht in einem unterstützten Header/Signaturformat gesendet. Wenn Hevy keine Verbindung herstellen kann, prüfe DNS, Port `443`, `HEVY_SYNC_DOMAIN` und die Caddy-Logs:

```bash
docker compose -f docker-compose.yaml logs -f caddy
```

Für lokale Tests direkt aus dem Arbeitsverzeichnis:

```bash
docker build -t hevy-sync:local .
docker run --rm -it --env-file .env -e DRY_RUN=true -v hevy-sync-test:/config hevy-sync:local hevy-sync
```

Lokaler Service-Test ohne Caddy:

```bash
docker run --rm -it --env-file .env -e DRY_RUN=true -p 8000:8000 -v hevy-sync-test:/config hevy-sync:local hevy-sync-service
curl http://localhost:8000/health
```

Hinweis: `docker run --env-file` interpretiert Anführungszeichen anders als Docker Compose. Die App normalisiert quoted Werte aus `.env`, damit beide Varianten funktionieren.

## Attribution

Teile der Sync-Funktionalität und die große Übungsmapping-Tabelle sind aus [drkostas/hevy2garmin](https://github.com/drkostas/hevy2garmin) adaptiert. Siehe [NOTICE.md](NOTICE.md).
