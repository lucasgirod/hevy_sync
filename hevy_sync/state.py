"""SQLite state store for Docker-friendly sync tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path


def _ts_newer(new_ts: str, old_ts: str) -> bool:
    try:
        new_dt = datetime.fromisoformat(new_ts.replace("Z", "+00:00"))
        old_dt = datetime.fromisoformat(old_ts.replace("Z", "+00:00"))
        return new_dt > old_dt
    except (ValueError, TypeError):
        return new_ts > old_ts


class SQLiteState:
    """SQLite-backed state compatible with the adapted hevy2garmin flow."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS synced_workouts (
                hevy_id TEXT PRIMARY KEY,
                garmin_activity_id TEXT,
                title TEXT,
                synced_at TEXT DEFAULT (datetime('now')),
                calories INTEGER,
                avg_hr INTEGER,
                status TEXT DEFAULT 'success',
                hevy_updated_at TEXT,
                sync_method TEXT DEFAULT 'upload'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TEXT DEFAULT (datetime('now')),
                synced INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                trigger TEXT DEFAULT 'manual'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hr_cache (
                hevy_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                cached_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        return conn

    def is_synced(self, hevy_id: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM synced_workouts WHERE hevy_id = ?", (hevy_id,)).fetchone()
        return row is not None

    def get_garmin_id(self, hevy_id: str) -> str | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT garmin_activity_id FROM synced_workouts WHERE hevy_id = ?", (hevy_id,)).fetchone()
        return row[0] if row else None

    def mark_synced(
        self,
        hevy_id: str,
        garmin_activity_id: str | None = None,
        title: str = "",
        calories: int | None = None,
        avg_hr: int | None = None,
        hevy_updated_at: str | None = None,
        sync_method: str = "upload",
    ) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO synced_workouts
                (hevy_id, garmin_activity_id, title, calories, avg_hr, hevy_updated_at, sync_method)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (hevy_id, garmin_activity_id, title, calories, avg_hr, hevy_updated_at, sync_method),
            )
            conn.commit()

    def get_stale_synced(self, workouts: list[dict]) -> list[str]:
        if not workouts:
            return []
        hevy_ids = [w.get("id", "") for w in workouts]
        placeholders = ",".join("?" for _ in hevy_ids)
        with self._get_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT hevy_id, hevy_updated_at
                FROM synced_workouts
                WHERE hevy_id IN ({placeholders}) AND hevy_updated_at IS NOT NULL
                """,
                hevy_ids,
            ).fetchall()
        stored = {row[0]: row[1] for row in rows}
        return [
            w.get("id", "")
            for w in workouts
            if stored.get(w.get("id", "")) and w.get("updated_at") and _ts_newer(w["updated_at"], stored[w.get("id", "")])
        ]

    def unsync(self, hevy_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM synced_workouts WHERE hevy_id = ?", (hevy_id,))
            conn.commit()
        return cur.rowcount > 0

    def unsync_all(self) -> int:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM synced_workouts")
            conn.commit()
        return cur.rowcount

    def get_synced_count(self) -> int:
        with self._get_conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM synced_workouts").fetchone()[0]

    def get_recent_synced(self, limit: int = 10) -> list[dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM synced_workouts ORDER BY synced_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def record_sync_log(self, synced: int = 0, skipped: int = 0, failed: int = 0, trigger: str = "manual") -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO sync_log (synced, skipped, failed, trigger) VALUES (?, ?, ?, ?)",
                (synced, skipped, failed, trigger),
            )
            conn.commit()

    def get_sync_log(self, limit: int = 20) -> list[dict]:
        with self._get_conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get_cached_hr(self, hevy_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT data FROM hr_cache WHERE hevy_id = ?", (hevy_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_hr(self, hevy_id: str, data: dict) -> None:
        with self._get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO hr_cache (hevy_id, data) VALUES (?, ?)", (hevy_id, json.dumps(data)))
            conn.commit()

    def get_app_config(self, key: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM app_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_app_config(self, key: str, value: dict) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_cache (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, json.dumps(value)),
            )
            conn.commit()
