from copy import deepcopy
from typing import Any

PRIVATE_ANSWER_KEYS = {
    "accepted_answers",
    "answer_key",
    "correct_answer",
    "correct_option_ids",
    "correct_order",
    "correct_pairs",
    "expected_answer",
}


def _sanitize_question(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    result = {
        key: deepcopy(item)
        for key, item in value.items()
        if key not in PRIVATE_ANSWER_KEYS
    }
    configuration = result.get("configuration")
    if isinstance(configuration, dict):
        result["configuration"] = {
            key: item
            for key, item in configuration.items()
            if key not in PRIVATE_ANSWER_KEYS
        }
    return result


def public_lesson_content(value: Any) -> dict[str, Any]:
    """Return compatibility content without private exercise answer keys."""
    if not isinstance(value, dict):
        return {}
    content = deepcopy(value)
    for field in ("practice_exercises", "writing_exercises", "questions"):
        items = content.get(field)
        if isinstance(items, list):
            content[field] = [_sanitize_question(item) for item in items]
    reading = content.get("reading")
    if isinstance(reading, dict) and isinstance(reading.get("questions"), list):
        reading["questions"] = [
            _sanitize_question(item) for item in reading["questions"]
        ]
    return content
