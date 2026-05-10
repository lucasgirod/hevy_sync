import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache

import fit_tool.profile.profile_type as profile_type
from fit_tool.profile.profile_type import ExerciseCategory

logger = logging.getLogger(__name__)

DEFAULT_WORKING_SET_SECONDS = 40
DEFAULT_WARMUP_SET_SECONDS = 25
DEFAULT_REST_BETWEEN_SETS_SECONDS = 75
DEFAULT_REST_BETWEEN_EXERCISES_SECONDS = 120

EXERCISE_ALIASES = {
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
        category, exercise_name, confidence = match_garmin_exercise(exercise.get("title", ""))
        if confidence < 0.65:
            logger.warning(
                "Low Garmin exercise match confidence for '%s': %s/%s (%.2f)",
                exercise.get("title", "Unknown"),
                category,
                exercise_name,
                confidence,
            )

        set_start = start + timedelta(seconds=cursor_seconds)
        set_duration = plan_item["set_duration"] * scale
        exercise_sets.append({
            "exercises": [{"category": category, "name": exercise_name}],
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
