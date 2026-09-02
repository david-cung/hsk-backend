from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Protocol

WRITING_TYPES = {
    "WORD_ORDER",
    "SENTENCE_REORDER",
    "TRANSLATION_TO_CHINESE",
    "GUIDED_WRITING",
}
WRITING_FILL_TYPE = "FILL_BLANK"
MAX_WRITING_ANSWER_LENGTH = 1000
CHINESE_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WHITESPACE_RE = re.compile(r"\s+")
PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "！": "!",
        "？": "?",
        "；": ";",
        "：": ":",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "、": ",",
        "（": "(",
        "）": ")",
    }
)
IGNORED_PUNCTUATION_RE = re.compile(r"""[\s,.!?;:'"()[\]{}，。！？；：“”‘’、（）《》〈〉【】]""")


@dataclass(frozen=True)
class WritingEvaluation:
    correct: bool
    score_ratio: float
    normalized_answer: str
    correct_answer: Any
    feedback: dict[str, Any]


class WritingEvaluationProvider(Protocol):
    provider_name: str

    def evaluate(self, question_type: str, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        ...


def normalize_writing_text(value: Any, *, compare: bool = False) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(PUNCTUATION_TRANSLATION).strip()
    text = WHITESPACE_RE.sub(" ", text)
    if compare:
        text = IGNORED_PUNCTUATION_RE.sub("", text)
    return text.strip()


def chinese_character_count(value: Any) -> int:
    return len(CHINESE_CHAR_RE.findall(str(value or "")))


def validate_writing_answer(answer: Any, config: dict[str, Any]) -> None:
    value = answer.get("value") if isinstance(answer, dict) and "value" in answer else answer
    limit = int(config.get("max_input_characters") or MAX_WRITING_ANSWER_LENGTH)
    if isinstance(value, str) and len(value) > min(limit, MAX_WRITING_ANSWER_LENGTH):
        raise ValueError("Writing answer is too long")


def validate_writing_config(question_type: str, config: dict[str, Any]) -> None:
    qtype = question_type.upper()
    if qtype in {"WORD_ORDER", "SENTENCE_REORDER"}:
        items = config.get("items") or config.get("tokens")
        if not isinstance(items, list) or not items:
            raise ValueError("items must be a non-empty list")
        item_ids = {str(item.get("id")) for item in items if isinstance(item, dict) and item.get("id")}
        if len(item_ids) != len(items):
            raise ValueError("each item requires a unique id")
        order = config.get("correct_order")
        expected = config.get("expected_answer") or config.get("expected_answers") or config.get("accepted_answers")
        if not isinstance(order, list) and not expected:
            raise ValueError("correct_order or expected_answers is required")
        if isinstance(order, list) and set(map(str, order)) != item_ids:
            raise ValueError("correct_order must include each item id exactly once")
    elif qtype in {"FILL_BLANK", "TRANSLATION_TO_CHINESE"}:
        answers = _answers(config)
        if not answers:
            raise ValueError("accepted_answers must contain at least one answer")
    elif qtype == "GUIDED_WRITING":
        min_chars = int(config.get("min_characters") or 0)
        max_chars = int(config.get("max_characters") or 0)
        if min_chars < 0 or max_chars < 0:
            raise ValueError("min_characters and max_characters must be non-negative")
        if max_chars and min_chars > max_chars:
            raise ValueError("min_characters cannot exceed max_characters")


class DeterministicWritingEvaluator:
    provider_name = "DETERMINISTIC"

    def evaluate(self, question_type: str, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        validate_writing_answer(answer, config)
        qtype = question_type.upper()
        if qtype == "WORD_ORDER":
            return self._word_order(answer, config)
        if qtype == "SENTENCE_REORDER":
            return self._sentence_reorder(answer, config)
        if qtype == "TRANSLATION_TO_CHINESE":
            return self._translation(answer, config)
        if qtype == "GUIDED_WRITING":
            return self._guided_writing(answer, config)
        return self._fill_blank(answer, config)

    def _fill_blank(self, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        raw = _raw_text(answer)
        normalized = normalize_writing_text(raw, compare=True)
        accepted = [normalize_writing_text(item, compare=True) for item in _answers(config)]
        correct = bool(normalized) and normalized in accepted
        return WritingEvaluation(
            correct=correct,
            score_ratio=1.0 if correct else 0.0,
            normalized_answer=normalized,
            correct_answer=_answers(config),
            feedback={
                "kind": "FILL_BLANK",
                "criteria": [_criterion("exact_match", correct, 100 if correct else 0)],
                "matched_tokens": [],
            },
        )

    def _word_order(self, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        selected_ids = [str(item) for item in answer] if isinstance(answer, list) else _ids_from_text(str(answer), config)
        correct_order = [str(item) for item in config.get("correct_order", [])]
        if not correct_order:
            fallback_expected = str((_answers(config) or [config.get("expected_answer") or ""])[0])
            correct_order = [item["id"] for item in _items(config) if item["text"] in fallback_expected]
        matches = [
            submitted == expected
            for submitted, expected in zip(selected_ids, correct_order, strict=False)
        ]
        exact = selected_ids == correct_order
        ratio = _sequence_ratio(selected_ids, correct_order)
        return WritingEvaluation(
            correct=exact,
            score_ratio=ratio if selected_ids else 0.0,
            normalized_answer="".join(_text_for_id(item, config) for item in selected_ids),
            correct_answer=correct_order,
            feedback={
                "kind": "WORD_ORDER",
                "criteria": [_criterion("token_order", exact, round(ratio * 100, 2))],
                "matched_tokens": [
                    {"id": item_id, "matched": matches[index] if index < len(matches) else False}
                    for index, item_id in enumerate(selected_ids)
                ],
            },
        )

    def _sentence_reorder(self, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        selected_ids = [str(item) for item in answer] if isinstance(answer, list) else _ids_from_text(str(answer), config)
        sentence = "".join(_text_for_id(item, config) for item in selected_ids) if selected_ids else _raw_text(answer)
        normalized = normalize_writing_text(sentence, compare=True)
        accepted = [normalize_writing_text(item, compare=True) for item in _answers(config)]
        correct = bool(normalized) and normalized in accepted
        ratio = 1.0 if correct else _best_character_overlap(normalized, accepted)
        return WritingEvaluation(
            correct=correct,
            score_ratio=ratio,
            normalized_answer=normalized,
            correct_answer=_answers(config),
            feedback={
                "kind": "SENTENCE_REORDER",
                "criteria": [_criterion("sentence_structure", correct, round(ratio * 100, 2))],
                "matched_tokens": [{"id": item_id, "text": _text_for_id(item_id, config)} for item_id in selected_ids],
            },
        )

    def _translation(self, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        raw = _raw_text(answer)
        normalized = normalize_writing_text(raw, compare=True)
        accepted = [normalize_writing_text(item, compare=True) for item in _answers(config)]
        exact = bool(normalized) and normalized in accepted
        keywords = [str(item) for item in config.get("required_keywords", []) if str(item).strip()]
        keyword_hits = [item for item in keywords if normalize_writing_text(item, compare=True) in normalized]
        keyword_ratio = len(keyword_hits) / len(keywords) if keywords else 0.0
        tolerance = float(config.get("keyword_tolerance", 1.0))
        keyword_correct = bool(config.get("accept_keyword_match")) and bool(keywords) and keyword_ratio >= tolerance
        ratio = 1.0 if exact else keyword_ratio
        return WritingEvaluation(
            correct=exact or keyword_correct,
            score_ratio=ratio,
            normalized_answer=normalized,
            correct_answer=_answers(config),
            feedback={
                "kind": "TRANSLATION_TO_CHINESE",
                "criteria": [
                    _criterion("accepted_answer", exact, 100 if exact else 0),
                    _criterion("required_keywords", not keywords or keyword_ratio >= tolerance, round(keyword_ratio * 100, 2)),
                ],
                "matched_tokens": keyword_hits,
                "missing_tokens": [item for item in keywords if item not in keyword_hits],
            },
        )

    def _guided_writing(self, answer: Any, config: dict[str, Any]) -> WritingEvaluation:
        raw = _raw_text(answer)
        normalized = normalize_writing_text(raw)
        comparable = normalize_writing_text(raw, compare=True)
        count = chinese_character_count(raw)
        non_space = len(re.sub(r"\s+", "", str(raw or "")))
        ratio = count / non_space if non_space else 0.0
        criteria = []
        min_chars = int(config.get("min_characters") or 0)
        max_chars = int(config.get("max_characters") or 0)
        if min_chars:
            criteria.append(_criterion("min_characters", count >= min_chars, 100 if count >= min_chars else _bounded(count / min_chars)))
        if max_chars:
            criteria.append(_criterion("max_characters", count <= max_chars, 100 if count <= max_chars else 0, actual=count, expected=max_chars))
        required_vocab = _string_list(config.get("required_vocabulary"))
        vocab_hits = [item for item in required_vocab if normalize_writing_text(item, compare=True) in comparable]
        if required_vocab:
            criteria.append(_coverage_criterion("required_vocabulary", vocab_hits, required_vocab))
        required_grammar = _string_list(config.get("required_grammar"))
        grammar_hits = [item for item in required_grammar if normalize_writing_text(item, compare=True) in comparable]
        if required_grammar:
            criteria.append(_coverage_criterion("required_grammar", grammar_hits, required_grammar))
        required_keywords = _string_list(config.get("required_keywords") or config.get("expected_concepts"))
        keyword_hits = [item for item in required_keywords if normalize_writing_text(item, compare=True) in comparable]
        if required_keywords:
            criteria.append(_coverage_criterion("required_keywords", keyword_hits, required_keywords))
        minimum_ratio = float(config.get("min_chinese_ratio", 0.6))
        criteria.append(_criterion("chinese_character_ratio", ratio >= minimum_ratio, round(_bounded(ratio / minimum_ratio), 2), actual=round(ratio, 2), expected=minimum_ratio))
        if not criteria:
            criteria.append(_criterion("non_empty", bool(comparable), 100 if comparable else 0))
        score = sum(float(item["score"]) for item in criteria) / len(criteria)
        passing = float(config.get("passing_score", 60))
        return WritingEvaluation(
            correct=score >= passing,
            score_ratio=score / 100,
            normalized_answer=normalized,
            correct_answer=None,
            feedback={
                "kind": "GUIDED_WRITING",
                "label": "STRUCTURED_EVALUATION",
                "criteria": criteria,
                "character_count": count,
                "chinese_character_ratio": round(ratio, 2),
                "matched_tokens": {
                    "vocabulary": vocab_hits,
                    "grammar": grammar_hits,
                    "keywords": keyword_hits,
                },
            },
        )


def writing_evaluator() -> WritingEvaluationProvider:
    return DeterministicWritingEvaluator()


def _answers(config: dict[str, Any]) -> list[str]:
    raw = config.get("accepted_answers") or config.get("expected_answers") or config.get("expected_answer") or []
    if isinstance(raw, str):
        return [raw]
    return [str(item) for item in raw if str(item).strip()] if isinstance(raw, list) else []


def _items(config: dict[str, Any]) -> list[dict[str, str]]:
    raw = config.get("items") or config.get("tokens") or []
    rows = []
    for index, item in enumerate(raw, start=1):
        if isinstance(item, dict):
            rows.append({"id": str(item.get("id") or index), "text": str(item.get("text") or item.get("value") or "")})
        else:
            rows.append({"id": str(index), "text": str(item)})
    return rows


def _raw_text(answer: Any) -> str:
    if isinstance(answer, dict) and "value" in answer:
        return str(answer["value"] or "")
    if isinstance(answer, list):
        return "".join(map(str, answer))
    return str(answer or "")


def _ids_from_text(value: str, config: dict[str, Any]) -> list[str]:
    remaining = normalize_writing_text(value, compare=True)
    selected = []
    for item in _items(config):
        text = normalize_writing_text(item["text"], compare=True)
        if text and text in remaining:
            selected.append(item["id"])
            remaining = remaining.replace(text, "", 1)
    return selected


def _text_for_id(item_id: str, config: dict[str, Any]) -> str:
    return next((item["text"] for item in _items(config) if item["id"] == str(item_id)), str(item_id))


def _sequence_ratio(selected: list[str], expected: list[str]) -> float:
    if not expected:
        return 0.0
    exact_positions = sum(1 for index, item in enumerate(expected) if index < len(selected) and selected[index] == item)
    missing_penalty = max(len(expected) - len(selected), 0)
    extra_penalty = max(len(selected) - len(expected), 0)
    return max((exact_positions - extra_penalty - missing_penalty) / len(expected), 0.0)


def _best_character_overlap(value: str, accepted: list[str]) -> float:
    if not value or not accepted:
        return 0.0
    return max(len(set(value) & set(candidate)) / max(len(set(candidate)), 1) for candidate in accepted)


def _criterion(
    key: str,
    passed: bool,
    score: float,
    *,
    actual: Any | None = None,
    expected: Any | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {"key": key, "passed": passed, "score": round(min(max(float(score), 0.0), 100.0), 2)}
    if actual is not None:
        row["actual"] = actual
    if expected is not None:
        row["expected"] = expected
    return row


def _coverage_criterion(key: str, hits: list[str], required: list[str]) -> dict[str, Any]:
    ratio = len(hits) / len(required) if required else 1
    row = _criterion(key, ratio >= 1, ratio * 100, actual=hits, expected=required)
    row["missing"] = [item for item in required if item not in hits]
    return row


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _bounded(value: float) -> float:
    return min(max(float(value) * 100, 0.0), 100.0)
