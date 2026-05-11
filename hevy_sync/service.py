"""Long-running scheduler and webhook service for hevy-sync."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import signal
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo

from .config import (
    RUN_ON_START,
    SERVER_HOST,
    SERVER_PORT,
    SYNC_CRON,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
)
from .sync_app import run_sync

logger = logging.getLogger(__name__)


class SyncRunner:
    """Serialize sync executions and coalesce concurrent triggers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._queued = False

    def request(self, trigger: str) -> str:
        with self._lock:
            if self._running:
                if not self._queued:
                    self._queued = True
                    logger.info("Sync läuft bereits; weiterer Trigger '%s' wurde queued.", trigger)
                    return "queued"
                logger.info("Sync läuft bereits; Trigger '%s' ist bereits queued.", trigger)
                return "already_queued"

            self._running = True
            thread = threading.Thread(target=self._worker, args=(trigger,), daemon=True)
            thread.start()
            return "started"

    def _worker(self, trigger: str) -> None:
        next_trigger = trigger
        while True:
            try:
                exit_code = run_sync(trigger=next_trigger)
                if exit_code:
                    logger.error("Sync-Run '%s' endete mit Exit-Code %s.", next_trigger, exit_code)
            except Exception:
                logger.exception("Sync-Run '%s' ist unerwartet fehlgeschlagen.", next_trigger)

            with self._lock:
                if self._queued:
                    self._queued = False
                    next_trigger = "queued"
                    continue
                self._running = False
                return

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running


class CronSchedule:
    """Minimal cron parser for expressions like '0 9,20 * * *'."""

    def __init__(self, expression: str, tz_name: str = "Europe/Zurich") -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError("SYNC_CRON muss fünf Felder haben, z.B. '0 9,20 * * *'.")
        minute, hour, day, month, weekday = parts
        if day != "*" or month != "*" or weekday != "*":
            raise ValueError("SYNC_CRON unterstützt aktuell nur tägliche Cron-Ausdrücke mit * * * in den letzten drei Feldern.")
        self.minutes = _parse_cron_field(minute, 0, 59)
        self.hours = _parse_cron_field(hour, 0, 23)
        self.tz = ZoneInfo(tz_name)
        self.expression = expression

    def next_after(self, now: datetime | None = None) -> datetime:
        current = now.astimezone(self.tz) if now else datetime.now(self.tz)
        candidate = (current + timedelta(minutes=1)).replace(second=0, microsecond=0)
        for _ in range(366 * 24 * 60):
            if candidate.hour in self.hours and candidate.minute in self.minutes:
                return candidate
            candidate += timedelta(minutes=1)
        raise RuntimeError(f"Kein nächster Zeitpunkt für Cron-Ausdruck {self.expression!r} gefunden.")


def _parse_cron_field(raw: str, minimum: int, maximum: int) -> set[int]:
    if raw == "*":
        return set(range(minimum, maximum + 1))

    values: set[int] = set()
    for part in raw.split(","):
        if "-" in part:
            start_raw, end_raw = part.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            values.update(range(start, end + 1))
        else:
            values.add(int(part))

    invalid = sorted(v for v in values if v < minimum or v > maximum)
    if invalid:
        raise ValueError(f"Ungültige Cron-Werte {invalid}; erlaubt ist {minimum}-{maximum}.")
    return values


def make_handler(runner: SyncRunner):
    webhook_path = WEBHOOK_PATH.rstrip("/") or "/webhook/hevy"

    class HevySyncHandler(BaseHTTPRequestHandler):
        server_version = "hevy-sync/1.0"

        def do_GET(self) -> None:
            if self.path.rstrip("/") in {"", "/health"}:
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "running": runner.running,
                        "webhook_path": webhook_path,
                    },
                )
                return
            self._send_json(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path.rstrip("/") != webhook_path:
                self._send_json(404, {"error": "not_found"})
                return

            raw_body = self.rfile.read(_content_length(self.headers))
            if not _valid_webhook_secret(self.headers, raw_body):
                self._send_json(401, {"error": "unauthorized"})
                return

            payload = _parse_json_body(raw_body)
            status = runner.request("webhook")
            self._send_json(
                202,
                {
                    "status": status,
                    "trigger": "webhook",
                    "event": _event_name(payload),
                },
            )

        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info("web %s - %s", self.address_string(), fmt % args)

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return HevySyncHandler


def _content_length(headers) -> int:
    try:
        return max(0, int(headers.get("Content-Length", "0")))
    except ValueError:
        return 0


def _parse_json_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _event_name(payload: dict[str, Any]) -> str | None:
    for key in ("event", "event_type", "type", "trigger"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _valid_webhook_secret(headers, raw_body: bytes) -> bool:
    if not WEBHOOK_SECRET:
        return True

    direct_values = [
        headers.get("X-Webhook-Secret"),
        headers.get("X-Hevy-Webhook-Secret"),
        headers.get("X-Hevy-Secret"),
    ]
    authorization = headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        direct_values.append(authorization[7:].strip())

    if any(hmac.compare_digest(value or "", WEBHOOK_SECRET) for value in direct_values):
        return True

    expected = hmac.new(WEBHOOK_SECRET.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    for header in ("X-Hevy-Signature", "X-Hub-Signature-256", "X-Signature"):
        signature = headers.get(header, "")
        if signature.startswith("sha256="):
            signature = signature.removeprefix("sha256=")
        if signature and hmac.compare_digest(signature, expected):
            return True

    return False


def start_scheduler(runner: SyncRunner, stop_event: threading.Event, tz_name: str) -> threading.Thread:
    schedule = CronSchedule(SYNC_CRON, tz_name)

    def loop() -> None:
        logger.info("Cron-Scheduler aktiv: %s (%s)", schedule.expression, tz_name)
        while not stop_event.is_set():
            next_run = schedule.next_after()
            logger.info("Nächster geplanter Sync: %s", next_run.isoformat())
            while not stop_event.is_set():
                remaining = (next_run - datetime.now(schedule.tz)).total_seconds()
                if remaining <= 0:
                    runner.request("cron")
                    break
                stop_event.wait(min(remaining, 60))

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def main() -> int:
    from .config import _env

    tz_name = _env("TZ", "Europe/Zurich") or "Europe/Zurich"
    runner = SyncRunner()
    stop_event = threading.Event()
    start_scheduler(runner, stop_event, tz_name)

    if RUN_ON_START:
        runner.request("startup")

    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), make_handler(runner))

    def stop(signum, _frame) -> None:
        logger.info("Signal %s erhalten; beende hevy-sync-service.", signum)
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    logger.info("Webhook-Service lauscht auf http://%s:%s%s", SERVER_HOST, SERVER_PORT, WEBHOOK_PATH)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        stop_event.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
