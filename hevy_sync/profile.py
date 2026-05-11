"""Resolve Garmin user profile values used for calorie estimation."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from garmin_auth import RateLimiter

logger = logging.getLogger(__name__)

_limiter = RateLimiter(delay=1.0, max_retries=2, base_wait=10)


def resolve_user_profile(
    client,
    fallback: dict[str, Any] | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Return calorie-estimation profile values, preferring Garmin data.

    The environment/config profile remains a fallback. Garmin's unofficial
    endpoints are not perfectly stable, so extraction intentionally accepts a
    few common shapes used by the profile, weight, and max-metrics APIs.
    """
    profile = dict(fallback or {})
    reference_date = reference_date or date.today()

    payloads: list[Any] = []
    for method_name in ("get_userprofile_settings", "get_user_profile"):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            payloads.append(_limiter.call(method))
        except Exception as exc:
            logger.debug("Garmin-Profilendpunkt %s nicht verfügbar: %s", method_name, exc)

    weight_payload = _fetch_weight_payload(client, reference_date)
    if weight_payload:
        payloads.append(weight_payload)

    birth_year = _extract_birth_year(payloads)
    weight_kg = _extract_weight_kg(payloads)
    vo2max = _fetch_vo2max(client, reference_date)

    sources = []
    if birth_year:
        profile["birth_year"] = birth_year
        sources.append("birth_year")
    if weight_kg:
        profile["weight_kg"] = weight_kg
        sources.append("weight_kg")
    if vo2max:
        profile["vo2max"] = vo2max
        sources.append("vo2max")

    if sources:
        logger.info(
            "Garmin-Profilwerte übernommen: %s%s",
            ", ".join(sources),
            _format_profile_summary(profile),
        )
    else:
        logger.info("Keine Garmin-Profilwerte gefunden; verwende Profil-Fallbacks aus Config.")

    return profile


def _fetch_weight_payload(client, reference_date: date) -> Any | None:
    start = (reference_date - timedelta(days=30)).isoformat()
    end = reference_date.isoformat()
    for method_name, args in (
        ("get_body_composition", (start, end)),
        ("get_weigh_ins", (start, end)),
        ("get_daily_weigh_ins", (end,)),
    ):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        try:
            return _limiter.call(method, *args)
        except Exception as exc:
            logger.debug("Garmin-Gewichtsendpunkt %s nicht verfügbar: %s", method_name, exc)
    return None


def _fetch_vo2max(client, reference_date: date) -> float | None:
    start = (reference_date - timedelta(days=90)).isoformat()
    end = reference_date.isoformat()

    connectapi = getattr(client, "connectapi", None)
    if callable(connectapi):
        try:
            payload = _limiter.call(
                connectapi,
                f"/metrics-service/metrics/maxmet/daily/{start}/{end}",
            )
            value = _extract_vo2max(payload)
            if value:
                return value
        except Exception as exc:
            logger.debug("Garmin-VO2Max-Zeitraum konnte nicht geladen werden: %s", exc)

    method = getattr(client, "get_max_metrics", None)
    if callable(method):
        try:
            return _extract_vo2max(_limiter.call(method, reference_date.isoformat()))
        except Exception as exc:
            logger.debug("Garmin-VO2Max-Tageswert konnte nicht geladen werden: %s", exc)

    return None


def _extract_birth_year(payloads: Iterable[Any]) -> int | None:
    for payload in payloads:
        for path, value in _walk(payload):
            if path[-1].lower() in {"birthdate", "dateofbirth", "dob", "birth_date"}:
                parsed = _parse_birth_year(value)
                if parsed:
                    return parsed
            if path[-1].lower() in {"birthyear", "birth_year"}:
                parsed = _parse_int(value)
                if parsed:
                    return parsed
    return None


def _extract_weight_kg(payloads: Iterable[Any]) -> float | None:
    best: float | None = None
    for payload in payloads:
        for path, value in _walk(payload):
            key = path[-1].lower()
            if key in {"weightkg", "weight_kg", "weightinkilograms"}:
                best = _parse_float(value) or best
            elif key in {"weightingrams", "weightgrams"}:
                grams = _parse_float(value)
                if grams:
                    best = grams / 1000.0
            elif key in {"weight", "value"} and any("weight" in p.lower() for p in path):
                unit_hint = " ".join(path).lower()
                normalized = _normalize_weight(value, unit_hint)
                if normalized:
                    best = normalized
    return round(best, 1) if best else None


def _extract_vo2max(payload: Any) -> float | None:
    best: float | None = None
    for path, value in _walk(payload):
        key = path[-1].lower()
        joined = ".".join(path).lower()
        if "vo2" not in joined:
            continue
        if key in {"vo2maxvalue", "vo2max", "value", "generic", "running", "cycling"}:
            parsed = _parse_float(value)
            if parsed and 10 <= parsed <= 100:
                best = parsed
    return round(best, 1) if best else None


def _normalize_weight(value: Any, unit_hint: str = "") -> float | None:
    parsed = _parse_float(value)
    if not parsed:
        return None
    if parsed > 1000:
        return parsed / 1000.0
    if any(token in unit_hint for token in ("lb", "pound", "imperial")):
        return parsed * 0.45359237
    if 20 <= parsed <= 250:
        return parsed
    return None


def _parse_birth_year(value: Any) -> int | None:
    if isinstance(value, int):
        return value if 1900 <= value <= date.today().year else None
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).year
        except ValueError:
            continue
    if len(value) >= 4 and value[:4].isdigit():
        year = int(value[:4])
        return year if 1900 <= year <= date.today().year else None
    return None


def _parse_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if 1900 <= parsed <= date.today().year else None


def _parse_float(value: Any) -> float | None:
    if isinstance(value, dict):
        for key in ("value", "amount", "weight", "fitnessValue"):
            parsed = _parse_float(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _walk(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, (*path, str(index)))
    else:
        yield path, value


def _format_profile_summary(profile: dict[str, Any]) -> str:
    parts = []
    for key, label in (
        ("birth_year", "Jahrgang"),
        ("weight_kg", "Gewicht"),
        ("vo2max", "VO2Max"),
    ):
        value = profile.get(key)
        if value is not None:
            suffix = " kg" if key == "weight_kg" else ""
            parts.append(f"{label}={value}{suffix}")
    return f" ({', '.join(parts)})" if parts else ""
