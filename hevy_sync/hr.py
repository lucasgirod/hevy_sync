"""Garmin daily heart-rate sampling for FIT generation."""

from __future__ import annotations

import logging

from garmin_auth import RateLimiter

from .fit import _parse_timestamp

logger = logging.getLogger(__name__)

_limiter = RateLimiter(delay=1.0, max_retries=3, base_wait=30)


def get_workout_hr_samples(client, workout: dict, state=None) -> list[int]:
    """Return Garmin daily HR samples sliced to the Hevy workout window."""
    hevy_id = workout.get("id")
    if state and hevy_id:
        cached = state.get_cached_hr(hevy_id)
        if cached and isinstance(cached.get("hr_values"), list):
            return [int(v) for v in cached["hr_values"]]

    start_raw = workout.get("start_time") or workout.get("startTime")
    end_raw = workout.get("end_time") or workout.get("endTime")
    start_dt = _parse_timestamp(start_raw)
    end_dt = _parse_timestamp(end_raw)
    if not start_dt or not end_dt:
        return []

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    date_str = start_raw[:10]

    try:
        daily_hr = _limiter.call(client.get_heart_rates, date_str)
    except Exception as exc:
        logger.warning("Konnte Garmin-Herzfrequenz für %s nicht laden: %s", date_str, exc)
        return []

    hr_values = daily_hr.get("heartRateValues", []) if isinstance(daily_hr, dict) else []
    samples = []
    timeline = []
    for entry in hr_values:
        if isinstance(entry, list) and len(entry) >= 2 and entry[1] is not None:
            ts, bpm = entry[0], entry[1]
            if start_ms - 60000 <= ts <= end_ms + 60000:
                samples.append(int(bpm))
                timeline.append({"time": max(0, (ts - start_ms) / 1000), "hr": int(bpm)})

    if state and hevy_id:
        state.cache_hr(hevy_id, {"hr_values": samples, "timeline": timeline})
    return samples
