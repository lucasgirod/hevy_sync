import json
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache
from importlib import resources

import fit_tool.profile.profile_type as profile_type
from fit_tool.profile.profile_type import ExerciseCategory

from .config import EXERCISE_MATCHES_FILE
from .mapper import (
    ensure_exercise_matches_file as _ensure_mapped_exercise_file,
    lookup_exercise_strings,
)

logger = logging.getLogger(__name__)

DEFAULT_WORKING_SET_SECONDS = 40
DEFAULT_WARMUP_SET_SECONDS = 25
DEFAULT_REST_BETWEEN_SETS_SECONDS = 75
DEFAULT_REST_BETWEEN_EXERCISES_SECONDS = 120
EXERCISE_MATCHES_SCHEMA_VERSION = 1

EXERCISE_ALIASES = {
    "beinpresse": ("SQUAT", "LEG_PRESS"),
    "brustpresse maschine": ("BENCH_PRESS", "DUMBBELL_BENCH_PRESS"),
    "chest press machine": ("BENCH_PRESS", "DUMBBELL_BENCH_PRESS"),
    "crunch maschine": ("CRUNCH", "WEIGHTED_CRUNCH"),
    "crunch machine": ("CRUNCH", "WEIGHTED_CRUNCH"),
    "hueftabduktion": ("HIP_STABILITY", "STANDING_HIP_ABDUCTION"),
    "hueftadduktion": ("HIP_STABILITY", "STANDING_ADDUCTION"),
    "huftabduktion": ("HIP_STABILITY", "STANDING_HIP_ABDUCTION"),
    "huftadduktion": ("HIP_STABILITY", "STANDING_ADDUCTION"),
    "hip abduction": ("HIP_STABILITY", "STANDING_HIP_ABDUCTION"),
    "hip adduction": ("HIP_STABILITY", "STANDING_ADDUCTION"),
    "latzug maschine": ("PULL_UP", "LAT_PULLDOWN"),
    "lat pulldown machine": ("PULL_UP", "LAT_PULLDOWN"),
    "liegendes beinbeugen maschine": ("LEG_CURL", "LEG_CURL"),
    "lying leg curl machine": ("LEG_CURL", "LEG_CURL"),
    "rueckenstrecken maschine": ("HYPEREXTENSION", "SPINE_EXTENSION"),
    "ruckenstrecken maschine": ("HYPEREXTENSION", "SPINE_EXTENSION"),
    "back extension machine": ("HYPEREXTENSION", "SPINE_EXTENSION"),
    "rudern sitzend maschine": ("ROW", "SEATED_CABLE_ROW"),
    "seated row machine": ("ROW", "SEATED_CABLE_ROW"),
    "schulterpresse sitzend maschine": ("SHOULDER_PRESS", "SEATED_DUMBBELL_SHOULDER_PRESS"),
    "seated shoulder press machine": ("SHOULDER_PRESS", "SEATED_DUMBBELL_SHOULDER_PRESS"),
    "beinstrecken": ("SQUAT", "LEG_PRESS"),
    "leg extension": ("SQUAT", "LEG_PRESS"),
    "leg extension machine": ("SQUAT", "LEG_PRESS"),
    "squat barbell": ("SQUAT", "BARBELL_BACK_SQUAT"),
    "back squat barbell": ("SQUAT", "BARBELL_BACK_SQUAT"),
    "front squat barbell": ("SQUAT", "BARBELL_FRONT_SQUAT"),
    "bicep curl dumbbell": ("CURL", "STANDING_DUMBBELL_BICEPS_CURL"),
    "biceps curl dumbbell": ("CURL", "STANDING_DUMBBELL_BICEPS_CURL"),
    "bicep curl barbell": ("CURL", "BARBELL_BICEPS_CURL"),
    "biceps curl barbell": ("CURL", "BARBELL_BICEPS_CURL"),
    "lat pulldown cable": ("PULL_UP", "LAT_PULLDOWN"),
    "bench press barbell": ("BENCH_PRESS", "BARBELL_BENCH_PRESS"),
    "bench press dumbbell": ("BENCH_PRESS", "DUMBBELL_BENCH_PRESS"),
}


def build_exercise_sets_payload(workout: dict, activity_id: int) -> dict:
    """Build Garmin's exerciseSets payload from a Hevy workout."""
    start = _parse_datetime(workout["start_time"])
    end = _parse_datetime(workout["end_time"])
    activity_duration = max((end - start).total_seconds(), 1)

    exercise_sets = []
    message_index = 0
    cursor_seconds = 0.0
    set_plan = _build_set_plan(workout)
    scale = _duration_scale(set_plan, activity_duration)

    for plan_item in set_plan:
        exercise = plan_item["exercise"]
        hevy_set = plan_item["set"]
        category, exercise_name, confidence, match_title = lookup_exercise_strings(exercise)
        if confidence < 0.65:
            logger.warning(
                "Low Garmin exercise match confidence for '%s' via '%s': %s/%s (%.2f)",
                exercise.get("title", "Unknown"),
                match_title,
                category,
                exercise_name,
                confidence,
            )

        set_start = start + timedelta(seconds=cursor_seconds)
        set_duration = plan_item["set_duration"] * scale
        exercise_sets.append({
            "exercises": [{"category": category, "name": exercise_name, "probability": 100.0}],
            "duration": round(set_duration, 3),
            "repetitionCount": _int_or_zero(hevy_set.get("reps")),
            "weight": _weight_grams(hevy_set.get("weight_kg")),
            "setType": "ACTIVE",
            "startTime": _garmin_time(set_start),
            "wktStepIndex": plan_item["exercise_index"],
            "messageIndex": message_index,
        })
        message_index += 1
        cursor_seconds += set_duration

        if plan_item["rest_duration"] > 0:
            rest_start = start + timedelta(seconds=cursor_seconds)
            rest_duration = plan_item["rest_duration"] * scale
            exercise_sets.append({
                "exercises": [],
                "duration": round(rest_duration, 3),
                "setType": "REST",
                "startTime": _garmin_time(rest_start),
                "wktStepIndex": plan_item["exercise_index"],
                "messageIndex": message_index,
            })
            message_index += 1
            cursor_seconds += rest_duration

    return {"activityId": activity_id, "exerciseSets": exercise_sets}


def ensure_exercise_matches_file() -> None:
    """Copy the bundled exercise mapping into the config directory if needed."""
    _ensure_mapped_exercise_file()


def match_garmin_exercise(title: str) -> tuple[str, str, float]:
    """Return Garmin exercise category/name strings for a Hevy exercise title."""
    normalized_title = _normalize(title)
    if not normalized_title:
        return "TOTAL_BODY", "TOTAL_BODY", 0.0
    if normalized_title in EXERCISE_ALIASES:
        category, exercise_name = EXERCISE_ALIASES[normalized_title]
        return category, exercise_name, 1.0

    best = ("TOTAL_BODY", "TOTAL_BODY", 0.0)
    for category, exercise_name, normalized_candidate in _garmin_exercise_candidates():
        score = _match_score(normalized_title, normalized_candidate)
        if score > best[2]:
            best = (category, exercise_name, score)

    if best[2] < 0.45:
        return "TOTAL_BODY", "TOTAL_BODY", best[2]
    return best


def match_garmin_exercise_for_hevy_exercise(exercise: dict) -> tuple[str, str, float, str]:
    configured_match = _match_configured_garmin_exercise(exercise)
    if configured_match:
        return configured_match

    best = ("TOTAL_BODY", "TOTAL_BODY", 0.0, "")
    for title in (exercise.get("title"), exercise.get("exercise_template_title"), exercise.get("name")):
        if not title:
            continue
        category, exercise_name, confidence = match_garmin_exercise(title)
        if confidence > best[2]:
            best = (category, exercise_name, confidence, title)

    _record_automatic_exercise_match(exercise, best)
    return best


def _build_set_plan(workout: dict) -> list[dict]:
    plan = []
    exercises = workout.get("exercises", [])
    for exercise_index, exercise in enumerate(exercises):
        sets = exercise.get("sets", [])
        for set_index, hevy_set in enumerate(sets):
            is_warmup = hevy_set.get("type") == "warmup"
            explicit_duration = hevy_set.get("duration_seconds")
            set_duration = float(explicit_duration or 0)
            if set_duration <= 0:
                set_duration = DEFAULT_WARMUP_SET_SECONDS if is_warmup else DEFAULT_WORKING_SET_SECONDS

            is_last_set = set_index == len(sets) - 1
            is_last_exercise = exercise_index == len(exercises) - 1
            if is_last_set and is_last_exercise:
                rest_duration = 0.0
            elif is_last_set:
                rest_duration = DEFAULT_REST_BETWEEN_EXERCISES_SECONDS
            else:
                rest_duration = DEFAULT_REST_BETWEEN_SETS_SECONDS

            plan.append({
                "exercise": exercise,
                "exercise_index": exercise_index,
                "set": hevy_set,
                "set_duration": set_duration,
                "rest_duration": rest_duration,
            })
    return plan


def _duration_scale(set_plan: list[dict], activity_duration: float) -> float:
    planned_duration = sum(item["set_duration"] + item["rest_duration"] for item in set_plan)
    if planned_duration <= 0:
        return 1.0
    return max(0.3, min(2.0, activity_duration / planned_duration))


@lru_cache(maxsize=1)
def _garmin_exercise_candidates() -> tuple[tuple[str, str, str], ...]:
    candidates = []
    for category in ExerciseCategory:
        if category.name == "UNKNOWN":
            continue
        enum_class = getattr(profile_type, _exercise_enum_name(category.name), None)
        if enum_class is None or not hasattr(enum_class, "__members__"):
            candidates.append((category.name, category.name, _normalize(category.name)))
            continue
        for exercise_name in enum_class.__members__:
            candidates.append((category.name, exercise_name, _normalize(exercise_name)))
    return tuple(candidates)


@lru_cache(maxsize=1)
def _valid_garmin_exercises() -> frozenset[tuple[str, str]]:
    return frozenset((category, exercise_name) for category, exercise_name, _ in _garmin_exercise_candidates())


def _match_configured_garmin_exercise(exercise: dict) -> tuple[str, str, float, str] | None:
    matches = _load_exercise_matches().get("matches", {})
    for title in _exercise_titles(exercise):
        key = _normalize(title)
        entry = matches.get(key)
        if not isinstance(entry, dict):
            continue

        category = entry.get("garmin_category")
        exercise_name = entry.get("garmin_exercise")
        if (category, exercise_name) not in _valid_garmin_exercises():
            logger.warning(
                "Ungültiges Garmin-Mapping für '%s' in %s: %s/%s",
                title,
                EXERCISE_MATCHES_FILE,
                category,
                exercise_name,
            )
            continue

        return category, exercise_name, 1.0, title
    return None


def _record_automatic_exercise_match(exercise: dict, match: tuple[str, str, float, str]) -> None:
    title = exercise.get("title") or match[3]
    key = _normalize(title)
    if not key:
        return

    data = _load_exercise_matches()
    matches = data.setdefault("matches", {})
    if key in matches:
        return

    category, exercise_name, confidence, match_title = match
    matches[key] = {
        "hevy_title": title,
        "hevy_template_title": exercise.get("exercise_template_title"),
        "garmin_category": category,
        "garmin_exercise": exercise_name,
        "confidence": round(confidence, 4),
        "matched_from": match_title,
        "source": "auto",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_exercise_matches(data)
    logger.info("Neues automatisches Garmin-Mapping für '%s' in %s gespeichert.", title, EXERCISE_MATCHES_FILE)


@lru_cache(maxsize=1)
def _load_exercise_matches() -> dict:
    _ensure_exercise_matches_file()
    try:
        data = json.loads(EXERCISE_MATCHES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Konnte Exercise-Mapping %s nicht laden: %s", EXERCISE_MATCHES_FILE, exc)
        return {"schema_version": EXERCISE_MATCHES_SCHEMA_VERSION, "matches": {}}

    if not isinstance(data, dict):
        return {"schema_version": EXERCISE_MATCHES_SCHEMA_VERSION, "matches": {}}
    if not isinstance(data.get("matches"), dict):
        data["matches"] = {}
    data.setdefault("schema_version", EXERCISE_MATCHES_SCHEMA_VERSION)
    return data


def _save_exercise_matches(data: dict) -> None:
    EXERCISE_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXERCISE_MATCHES_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
            _save_exercise_matches(existing_data)
            logger.info("%s neue Repository-Mappings nach %s übernommen.", len(missing_seed_matches), EXERCISE_MATCHES_FILE)
        return

    EXERCISE_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXERCISE_MATCHES_FILE.write_text(
        json.dumps(seed_data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    logger.info("Exercise-Mapping aus dem Repository nach %s kopiert.", EXERCISE_MATCHES_FILE)


def _exercise_titles(exercise: dict) -> tuple[str, ...]:
    titles = []
    for title in (exercise.get("title"), exercise.get("exercise_template_title"), exercise.get("name")):
        if title and title not in titles:
            titles.append(title)
    return tuple(titles)


def _exercise_enum_name(category_name: str) -> str:
    return "".join(part.title() for part in category_name.split("_")) + "ExerciseName"


def _match_score(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    token_overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    ordered = SequenceMatcher(None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))).ratio()
    direct = SequenceMatcher(None, left, right).ratio()
    return max(direct, (token_overlap * 0.75) + (ordered * 0.25))


def _normalize(value: str) -> str:
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


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _garmin_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.0")


def _int_or_zero(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _weight_grams(value) -> float:
    try:
        return float(round(float(value) * 1000))
    except (TypeError, ValueError):
        return 0.0
