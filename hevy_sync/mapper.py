"""Hevy-to-Garmin exercise mapping.

Seed data is adapted from drkostas/hevy2garmin (MIT licensed) and stored in
``hevy_sync/data/exercise_matches.json``. At runtime the seed is copied to the
config volume so user corrections survive image updates.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from importlib import resources

import fit_tool.profile.profile_type as profile_type
from fit_tool.profile.profile_type import ExerciseCategory

from .config import EXERCISE_MATCHES_FILE

logger = logging.getLogger(__name__)

UNKNOWN_CATEGORY_ID = 65534
UNKNOWN_EXERCISE_ID = 0


def ensure_exercise_matches_file() -> None:
    """Copy and merge the bundled mapping into the config directory."""
    _ensure_exercise_matches_file()
    _load_exercise_matches.cache_clear()


def lookup_exercise(exercise: str | dict) -> tuple[int, int, str]:
    """Return ``(category_id, exercise_id, display_name)`` for a Hevy exercise."""
    configured = _lookup_configured_exercise(exercise)
    if configured:
        return configured

    title = _primary_title(exercise)
    category, exercise_name, confidence = _auto_match_exercise(title)
    if confidence >= 0.78:
        _record_automatic_exercise_match(exercise, category, exercise_name, confidence, title)
        return _ids_for_pair(category, exercise_name) + (title,)

    _record_unmapped_exercise(exercise, title)
    return UNKNOWN_CATEGORY_ID, UNKNOWN_EXERCISE_ID, title


def lookup_exercise_strings(exercise: str | dict) -> tuple[str, str, float, str]:
    """Return Garmin API category/name strings for exerciseSets payloads."""
    configured = _lookup_configured_entry(exercise)
    if configured:
        entry, title = configured
        return entry["garmin_category"], entry["garmin_exercise"], 1.0, title

    title = _primary_title(exercise)
    category, exercise_name, confidence = _auto_match_exercise(title)
    if confidence >= 0.78:
        _record_automatic_exercise_match(exercise, category, exercise_name, confidence, title)
        return category, exercise_name, confidence, title

    _record_unmapped_exercise(exercise, title)
    return "TOTAL_BODY", "TOTAL_BODY", confidence, title


def normalize_title(value: str) -> str:
    """Normalize a Hevy/Garmin exercise title for lookup."""
    value = value.replace("N3", "3").replace("N45", "45").replace("N90", "90")
    value = value.translate(str.maketrans({
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "Ä": "ae",
        "Ö": "oe",
        "Ü": "ue",
        "ß": "ss",
    }))
    value = re.sub(r"\bbicep\b", "biceps", value, flags=re.IGNORECASE)
    value = re.sub(r"[^a-zA-Z0-9]+", " ", value).lower()
    return " ".join(value.split())


def _lookup_configured_exercise(exercise: str | dict) -> tuple[int, int, str] | None:
    configured = _lookup_configured_entry(exercise)
    if not configured:
        return None
    entry, title = configured
    category = entry.get("garmin_category")
    exercise_name = entry.get("garmin_exercise")
    if not category or not exercise_name:
        return None
    return _ids_for_pair(category, exercise_name) + (title,)


def _lookup_configured_entry(exercise: str | dict) -> tuple[dict, str] | None:
    matches = _load_exercise_matches().get("matches", {})
    for title in _exercise_titles(exercise):
        entry = matches.get(normalize_title(title))
        if not isinstance(entry, dict):
            continue

        category = entry.get("garmin_category")
        exercise_name = entry.get("garmin_exercise")
        if (category, exercise_name) not in _valid_garmin_pairs():
            logger.warning(
                "Ungültiges Garmin-Mapping für '%s' in %s: %s/%s",
                title,
                EXERCISE_MATCHES_FILE,
                category,
                exercise_name,
            )
            continue
        return entry, title
    return None


def _record_automatic_exercise_match(
    exercise: str | dict,
    category: str,
    exercise_name: str,
    confidence: float,
    matched_from: str,
) -> None:
    title = _primary_title(exercise)
    key = normalize_title(title)
    if not key:
        return

    data = _load_exercise_matches()
    matches = data.setdefault("matches", {})
    if key in matches:
        return

    category_id, exercise_id = _ids_for_pair(category, exercise_name)
    matches[key] = {
        "hevy_title": title,
        "hevy_template_title": _template_title(exercise),
        "garmin_category": category,
        "garmin_exercise": exercise_name,
        "garmin_category_id": category_id,
        "garmin_exercise_id": exercise_id,
        "confidence": round(confidence, 4),
        "matched_from": matched_from,
        "source": "auto",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_exercise_matches(data)
    logger.info("Neues automatisches Garmin-Mapping für '%s' in %s gespeichert.", title, EXERCISE_MATCHES_FILE)


def _record_unmapped_exercise(exercise: str | dict, matched_from: str) -> None:
    title = _primary_title(exercise)
    key = normalize_title(title)
    if not key:
        return

    data = _load_exercise_matches()
    matches = data.setdefault("matches", {})
    if key in matches:
        return

    matches[key] = {
        "hevy_title": title,
        "hevy_template_title": _template_title(exercise),
        "garmin_category": "UNKNOWN",
        "garmin_exercise": "UNKNOWN",
        "garmin_category_id": UNKNOWN_CATEGORY_ID,
        "garmin_exercise_id": UNKNOWN_EXERCISE_ID,
        "matched_from": matched_from,
        "source": "unmapped",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_exercise_matches(data)
    logger.warning("Keine Garmin-Übung für '%s' gefunden; als UNKNOWN in %s gespeichert.", title, EXERCISE_MATCHES_FILE)


@lru_cache(maxsize=1)
def _load_exercise_matches() -> dict:
    _ensure_exercise_matches_file()
    try:
        data = json.loads(EXERCISE_MATCHES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Konnte Exercise-Mapping %s nicht laden: %s", EXERCISE_MATCHES_FILE, exc)
        return {"schema_version": 2, "matches": {}}

    if not isinstance(data, dict):
        return {"schema_version": 2, "matches": {}}
    if not isinstance(data.get("matches"), dict):
        data["matches"] = {}
    return data


def _save_exercise_matches(data: dict) -> None:
    EXERCISE_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXERCISE_MATCHES_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _load_exercise_matches.cache_clear()


def _ensure_exercise_matches_file() -> None:
    seed = resources.files("hevy_sync.data").joinpath("exercise_matches.json")
    seed_data = json.loads(seed.read_text(encoding="utf-8"))
    if EXERCISE_MATCHES_FILE.exists():
        try:
            existing_data = json.loads(EXERCISE_MATCHES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Bestehendes Exercise-Mapping %s konnte nicht gemerged werden: %s",
                EXERCISE_MATCHES_FILE,
                exc,
            )
            return

        existing_matches = existing_data.setdefault("matches", {})
        seed_matches = seed_data.get("matches", {})
        missing_seed_matches = {
            key: value
            for key, value in seed_matches.items()
            if key not in existing_matches
        }
        if missing_seed_matches:
            existing_matches.update(missing_seed_matches)
            EXERCISE_MATCHES_FILE.write_text(
                json.dumps(existing_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            logger.info("%s neue Repository-Mappings nach %s übernommen.", len(missing_seed_matches), EXERCISE_MATCHES_FILE)
        return

    EXERCISE_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXERCISE_MATCHES_FILE.write_text(
        json.dumps(seed_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    logger.info("Exercise-Mapping aus dem Repository nach %s kopiert.", EXERCISE_MATCHES_FILE)


def _primary_title(exercise: str | dict) -> str:
    return next(iter(_exercise_titles(exercise)), "Unknown")


def _template_title(exercise: str | dict) -> str | None:
    if isinstance(exercise, dict):
        return exercise.get("exercise_template_title")
    return None


def _exercise_titles(exercise: str | dict) -> tuple[str, ...]:
    if isinstance(exercise, str):
        return (exercise,) if exercise else ()

    titles = []
    for title in (exercise.get("title"), exercise.get("exercise_template_title"), exercise.get("name")):
        if title and title not in titles:
            titles.append(title)
    return tuple(titles)


@lru_cache(maxsize=1)
def _garmin_candidates() -> tuple[tuple[str, str, str], ...]:
    candidates = []
    for category in ExerciseCategory:
        if category.name == "UNKNOWN":
            continue
        enum_class = getattr(profile_type, _exercise_enum_name(category.name), None)
        if enum_class is None or not hasattr(enum_class, "__members__"):
            candidates.append((category.name, category.name, normalize_title(category.name)))
            continue
        for exercise_name in enum_class.__members__:
            candidates.append((category.name, exercise_name, normalize_title(exercise_name)))
    return tuple(candidates)


@lru_cache(maxsize=1)
def _valid_garmin_pairs() -> frozenset[tuple[str, str]]:
    pairs = {(category, exercise_name) for category, exercise_name, _ in _garmin_candidates()}
    pairs.add(("UNKNOWN", "UNKNOWN"))
    return frozenset(pairs)


def _auto_match_exercise(title: str) -> tuple[str, str, float]:
    normalized = normalize_title(title)
    if not normalized:
        return "TOTAL_BODY", "TOTAL_BODY", 0.0

    best = ("TOTAL_BODY", "TOTAL_BODY", 0.0)
    for category, exercise_name, candidate in _garmin_candidates():
        score = _match_score(normalized, candidate)
        if score > best[2]:
            best = (category, exercise_name, score)
    return best


def _ids_for_pair(category: str, exercise_name: str) -> tuple[int, int]:
    if category == "UNKNOWN":
        return UNKNOWN_CATEGORY_ID, UNKNOWN_EXERCISE_ID

    category_id = ExerciseCategory[category].value
    enum_class = getattr(profile_type, _exercise_enum_name(category), None)
    if enum_class is None or not hasattr(enum_class, "__members__"):
        return category_id, 0
    return category_id, enum_class[exercise_name].value


def _exercise_enum_name(category_name: str) -> str:
    return "".join(part.title() for part in category_name.split("_")) + "ExerciseName"


def _match_score(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    token_overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    ordered = SequenceMatcher(None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))).ratio()
    direct = SequenceMatcher(None, left, right).ratio()
    return max(direct, (token_overlap * 0.75) + (ordered * 0.25))
