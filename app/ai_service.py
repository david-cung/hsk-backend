from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.ai_context import build_tutor_context
from app.ai_prompts import (
    MODE_TITLES,
    PROMPT_VERSION,
    ROLE_PLAY_SCENARIOS,
    grammar_system_prompt,
    scenario_by_id,
    sentence_system_prompt,
    tutor_system_prompt,
    writing_system_prompt,
)
from app.ai_provider import (
    CHAT_SCHEMA_NAME,
    GRAMMAR_SCHEMA_NAME,
    SENTENCE_SCHEMA_NAME,
    WRITING_SCHEMA_NAME,
    AIProviderResult,
    AITutorError,
    AITutorProvider,
    get_ai_provider,
    parse_structured_payload,
)
from app.config import settings
from app.gamification_service import record_event
from app.models import (
    AiUsageEvent,
    Conversation,
    ConversationMessage,
    ConversationMessageRole,
    ConversationMode,
    Course,
    GrammarPoint,
    Lesson,
    User,
    Vocabulary,
)
from app.review_scheduler import ReviewRating
from app.review_service import enroll_card, review_card
from app.skill_schemas import (
    ConversationListOut,
    ConversationMessageOut,
    ConversationMessageResultOut,
    ConversationOut,
    GrammarExplainOut,
    SentenceCheckOut,
    WritingFeedbackOut,
)

logger = logging.getLogger("hsk.ai")

CONVERSATION_MODES = {item.value for item in ConversationMode}
MESSAGE_ACTIONS = {None, "reply", "explain", "correct", "pinyin", "translate"}
EXPLANATION_LANGUAGES = {"zh", "pinyin", "vi", "en"}
USER_FACING_ERRORS = {
    "TIMEOUT": "The tutor is taking too long to reply. Please try again.",
    "RATE_LIMIT": "Please wait a moment before sending another message.",
    "PROVIDER_UNAVAILABLE": "The tutor is temporarily unavailable.",
    "PROVIDER_ERROR": "The tutor could not complete this request.",
    "NETWORK": "The tutor is temporarily unavailable.",
    "INVALID_RESPONSE": "The tutor returned an invalid reply. Please try again.",
    "MALFORMED_JSON": "The tutor returned an invalid reply. Please try again.",
    "INPUT_TOO_LONG": "That message is too long.",
}


class AITutorServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def list_scenarios() -> list[dict[str, Any]]:
    return ROLE_PLAY_SCENARIOS


def create_conversation(
    db: Session,
    user: User,
    *,
    mode: str,
    lesson_id: int | None = None,
    course_id: int | None = None,
    hsk_level: int | None = None,
    scenario_id: str | None = None,
    explanation_language: str = "zh",
    title: str | None = None,
) -> Conversation:
    normalized_mode = (mode or "").upper()
    if normalized_mode not in CONVERSATION_MODES:
        raise AITutorServiceError(422, "Unsupported conversation mode")
    language = (explanation_language or "zh").lower()
    if language not in EXPLANATION_LANGUAGES:
        raise AITutorServiceError(422, "Unsupported explanation language")
    if normalized_mode == ConversationMode.ROLE_PLAY.value and not scenario_by_id(scenario_id):
        raise AITutorServiceError(422, "Choose a role-play scenario")
    if scenario_id and normalized_mode != ConversationMode.ROLE_PLAY.value:
        raise AITutorServiceError(422, "Scenarios are only used in role play")
    profile_level = user.profile.current_hsk_level if user.profile else 1
    level = int(hsk_level or profile_level or 1)
    lesson = _owned_lesson(db, lesson_id)
    course = _owned_course(db, course_id or (lesson.course_id if lesson else None))
    if lesson and course is None:
        course = lesson.course
    conversation = Conversation(
        user_id=user.id,
        mode=normalized_mode,
        hsk_level=max(1, min(level, 6)),
        course_id=course.id if course else None,
        lesson_id=lesson.id if lesson else None,
        title=(title or _default_title(normalized_mode, scenario_id, lesson))[:180],
        scenario_id=scenario_id if normalized_mode == ConversationMode.ROLE_PLAY.value else None,
        explanation_language=language,
        prompt_version=settings.ai_tutor_prompt_version or PROMPT_VERSION,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(db: Session, user: User, *, limit: int = 20, offset: int = 0) -> ConversationListOut:
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))
    total = db.scalar(select(func.count(Conversation.id)).where(Conversation.user_id == user.id)) or 0
    rows = db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return ConversationListOut(
        items=[conversation_to_out(item, include_messages=False) for item in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def get_conversation(db: Session, user: User, conversation_id: int) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    if conversation is None:
        raise AITutorServiceError(404, "Conversation not found")
    return conversation


def delete_conversation(db: Session, user: User, conversation_id: int) -> None:
    conversation = get_conversation(db, user, conversation_id)
    db.delete(conversation)
    db.commit()


def send_message(
    db: Session,
    user: User,
    conversation_id: int,
    *,
    content: str,
    action: str | None = None,
    idempotency_key: str | None = None,
    provider: AITutorProvider | None = None,
) -> ConversationMessageResultOut:
    conversation = get_conversation(db, user, conversation_id)
    text = (content or "").strip()
    _validate_input(text)
    normalized_action = (action or "reply").lower()
    if normalized_action not in {item for item in MESSAGE_ACTIONS if item}:
        raise AITutorServiceError(422, "Unsupported message action")
    if idempotency_key:
        existing = _existing_turn(db, conversation.id, idempotency_key)
        if existing:
            user_message, assistant_message = existing
            return ConversationMessageResultOut(
                conversation=conversation_to_out(conversation),
                user_message=message_to_out(user_message),
                assistant_message=message_to_out(assistant_message),
            )
    _enforce_rate_limit(db, user.id)
    context = build_tutor_context(db, user, conversation=conversation)
    history = _history_messages(conversation)
    prompt = tutor_system_prompt(
        mode=conversation.mode,
        hsk_level=conversation.hsk_level,
        explanation_language=conversation.explanation_language,
        scenario_id=conversation.scenario_id,
        context=context,
        action=normalized_action,
    )
    result = _call_provider(
        db,
        user,
        provider or get_ai_provider(),
        messages=[*history, {"role": "user", "content": text}],
        system_prompt=prompt,
        schema_name=CHAT_SCHEMA_NAME,
        operation="chat",
        conversation_id=conversation.id,
    )
    payload = _conversation_payload(result, text)
    user_message = ConversationMessage(
        conversation_id=conversation.id,
        role=ConversationMessageRole.USER.value,
        content=text,
        structured_payload={"action": normalized_action},
        idempotency_key=idempotency_key,
    )
    assistant_message = ConversationMessage(
        conversation_id=conversation.id,
        role=ConversationMessageRole.ASSISTANT.value,
        content=str(payload.get("message") or payload.get("chinese_text") or ""),
        structured_payload=payload,
        token_usage=_token_usage(result),
        prompt_version=conversation.prompt_version,
    )
    db.add(user_message)
    db.add(assistant_message)
    conversation.updated_at = datetime.now(UTC)
    if conversation.title in MODE_TITLES.values() or conversation.title.startswith("Role play"):
        conversation.title = text[:80]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        conversation = get_conversation(db, user, conversation_id)
        existing = _existing_turn(db, conversation.id, idempotency_key) if idempotency_key else None
        if not existing:
            raise AITutorServiceError(409, "Could not save this message") from None
        user_message, assistant_message = existing
        return ConversationMessageResultOut(
            conversation=conversation_to_out(conversation),
            user_message=message_to_out(user_message),
            assistant_message=message_to_out(assistant_message),
        )
    db.refresh(conversation)
    db.refresh(user_message)
    db.refresh(assistant_message)
    _record_learning_signals(db, user, payload)
    record_event(
        db,
        user,
        "AI_CONVERSATION_COMPLETED",
        f"conversation:{conversation.id}",
        minutes=1,
    )
    db.commit()
    return ConversationMessageResultOut(
        conversation=conversation_to_out(conversation),
        user_message=message_to_out(user_message),
        assistant_message=message_to_out(assistant_message),
    )


def check_sentence(
    db: Session,
    user: User,
    *,
    sentence: str,
    lesson_id: int | None = None,
    provider: AITutorProvider | None = None,
) -> SentenceCheckOut:
    text = (sentence or "").strip()
    _validate_input(text)
    _enforce_rate_limit(db, user.id)
    context = build_tutor_context(db, user, lesson_id=lesson_id)
    result = _call_provider(
        db,
        user,
        provider or get_ai_provider(),
        messages=[{"role": "user", "content": text}],
        system_prompt=sentence_system_prompt(user.profile.current_hsk_level, context),
        schema_name=SENTENCE_SCHEMA_NAME,
        operation="sentence_check",
    )
    payload = result.payload or {}
    response = SentenceCheckOut(
        corrected_sentence=str(payload.get("corrected_sentence") or text),
        is_correct=_as_bool(payload.get("is_correct"), False),
        explanation=str(payload.get("explanation") or "No explanation available."),
        alternatives=_string_list(payload.get("alternatives")),
        vocabulary_notes=_dict_list(payload.get("vocabulary_notes")),
        grammar_notes=_dict_list(payload.get("grammar_notes")),
    )
    _record_learning_signals(
        db,
        user,
        {
            "vocabulary_notes": response.vocabulary_notes,
            "grammar_notes": response.grammar_notes,
            "corrections": [] if response.is_correct else [{"note": "sentence"}],
        },
    )
    db.commit()
    return response


def explain_grammar(
    db: Session,
    user: User,
    *,
    grammar_point: str,
    sentence: str | None = None,
    lesson_id: int | None = None,
    provider: AITutorProvider | None = None,
) -> GrammarExplainOut:
    point = (grammar_point or "").strip()
    _validate_input(point)
    if sentence:
        _validate_input(sentence)
    _enforce_rate_limit(db, user.id)
    context = build_tutor_context(db, user, lesson_id=lesson_id)
    user_content = point if not sentence else f"{point}\n{sentence}"
    result = _call_provider(
        db,
        user,
        provider or get_ai_provider(),
        messages=[{"role": "user", "content": user_content}],
        system_prompt=grammar_system_prompt(user.profile.current_hsk_level, context),
        schema_name=GRAMMAR_SCHEMA_NAME,
        operation="grammar_explain",
    )
    payload = result.payload or {}
    return GrammarExplainOut(
        is_correct=None if payload.get("is_correct") is None else _as_bool(payload.get("is_correct"), False),
        corrected_sentence=str(payload.get("corrected_sentence") or "") or None,
        explanation=str(payload.get("explanation") or "No explanation available."),
        examples=_string_list(payload.get("examples")),
        difficulty=str(payload.get("difficulty") or "") or None,
    )


def writing_feedback(
    db: Session,
    user: User,
    *,
    answer: str,
    prompt: str | None = None,
    lesson_id: int | None = None,
    provider: AITutorProvider | None = None,
) -> WritingFeedbackOut:
    text = (answer or "").strip()
    _validate_input(text)
    _enforce_rate_limit(db, user.id)
    context = build_tutor_context(db, user, lesson_id=lesson_id)
    user_content = text if not prompt else f"{prompt}\n{text}"
    result = _call_provider(
        db,
        user,
        provider or get_ai_provider(),
        messages=[{"role": "user", "content": user_content}],
        system_prompt=writing_system_prompt(user.profile.current_hsk_level, context),
        schema_name=WRITING_SCHEMA_NAME,
        operation="writing_feedback",
    )
    return writing_payload_to_out(result.payload)


def writing_payload_to_out(payload: dict[str, Any] | None) -> WritingFeedbackOut:
    data = payload or {}
    score = _optional_int(data.get("score"))
    return WritingFeedbackOut(
        label="AI Feedback",
        score=max(0, min(score, 100)) if score is not None else None,
        corrected_answer=str(data.get("corrected_answer") or "") or None,
        strengths=_string_list(data.get("strengths")),
        mistakes=_string_list(data.get("mistakes")),
        grammar_feedback=_string_list(data.get("grammar_feedback")),
        vocabulary_feedback=_string_list(data.get("vocabulary_feedback")),
        suggestions=_string_list(data.get("suggestions")),
    )


def ai_usage_summary(db: Session, *, user_id: int | None = None) -> dict[str, Any]:
    query = select(
        func.count(AiUsageEvent.id),
        func.coalesce(func.sum(AiUsageEvent.input_tokens), 0),
        func.coalesce(func.sum(AiUsageEvent.output_tokens), 0),
        func.coalesce(func.avg(AiUsageEvent.latency_ms), 0),
    )
    if user_id is not None:
        query = query.where(AiUsageEvent.user_id == user_id)
    count, input_tokens, output_tokens, latency = db.execute(query).one()
    return {
        "requests": int(count or 0),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "average_latency_ms": int(latency or 0),
    }


def conversation_metrics(db: Session, user_id: int) -> dict[str, int]:
    conversations = db.scalar(select(func.count(Conversation.id)).where(Conversation.user_id == user_id)) or 0
    messages = db.scalar(
        select(func.count(ConversationMessage.id))
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .where(Conversation.user_id == user_id, ConversationMessage.role != ConversationMessageRole.SYSTEM.value)
    ) or 0
    corrections = db.scalar(
        select(func.count(AiUsageEvent.id)).where(
            AiUsageEvent.user_id == user_id,
            AiUsageEvent.operation.in_(("sentence_check", "grammar_explain", "writing_feedback")),
        )
    ) or 0
    return {
        "ai_conversations": int(conversations),
        "ai_messages": int(messages),
        "ai_corrections": int(corrections),
    }


def conversation_to_out(conversation: Conversation, *, include_messages: bool = True) -> ConversationOut:
    messages = []
    if include_messages:
        messages = [
            message_to_out(item)
            for item in conversation.messages
            if item.role != ConversationMessageRole.SYSTEM.value
        ]
    return ConversationOut(
        id=conversation.id,
        mode=conversation.mode,
        hsk_level=conversation.hsk_level,
        course_id=conversation.course_id,
        lesson_id=conversation.lesson_id,
        title=conversation.title,
        scenario_id=conversation.scenario_id,
        explanation_language=conversation.explanation_language,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


def message_to_out(message: ConversationMessage) -> ConversationMessageOut:
    payload = message.structured_payload or {}
    return ConversationMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        chinese_text=payload.get("chinese_text"),
        pinyin=payload.get("pinyin"),
        translation=payload.get("translation"),
        corrections=_dict_list(payload.get("corrections")),
        vocabulary_notes=_dict_list(payload.get("vocabulary_notes")),
        grammar_notes=_dict_list(payload.get("grammar_notes")),
        prompt_version=message.prompt_version,
        created_at=message.created_at,
    )


def _call_provider(
    db: Session,
    user: User,
    provider: AITutorProvider,
    *,
    messages: list[dict[str, str]],
    system_prompt: str,
    schema_name: str,
    operation: str,
    conversation_id: int | None = None,
) -> AIProviderResult:
    attempts = max(1, settings.ai_retry_attempts + 1)
    last_error: AITutorError | None = None
    started = time.monotonic()
    for attempt in range(attempts):
        try:
            result = provider.generate_response(
                messages,
                system_prompt=system_prompt,
                schema_name=schema_name,
                max_tokens=settings.ai_max_tokens,
                temperature=settings.ai_temperature,
                timeout=settings.ai_timeout,
            )
            if not result.payload:
                result = AIProviderResult(
                    text=result.text,
                    payload=parse_structured_payload(result.text),
                    provider=result.provider,
                    model=result.model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                    raw_metadata=result.raw_metadata,
                )
            _record_usage(
                db,
                user.id,
                operation=operation,
                provider=result.provider,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=result.latency_ms or int((time.monotonic() - started) * 1000),
                conversation_id=conversation_id,
            )
            return result
        except AITutorError as exc:
            last_error = exc
            _record_usage(
                db,
                user.id,
                operation=operation,
                provider=getattr(provider, "name", "unknown"),
                model=getattr(provider, "model", settings.ai_model),
                latency_ms=int((time.monotonic() - started) * 1000),
                error_code=exc.code,
                conversation_id=conversation_id,
            )
            if not exc.retryable or attempt >= attempts - 1:
                raise AITutorServiceError(
                    503 if exc.retryable else 502, _public_error(exc)
                ) from exc
    raise AITutorServiceError(503, _public_error(last_error)) from last_error


def _record_usage(
    db: Session,
    user_id: int,
    *,
    operation: str,
    provider: str,
    model: str | None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    error_code: str | None = None,
    conversation_id: int | None = None,
) -> None:
    db.add(
        AiUsageEvent(
            user_id=user_id,
            conversation_id=conversation_id,
            operation=operation,
            provider=provider,
            model=model,
            prompt_version=settings.ai_tutor_prompt_version or PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            error_code=error_code,
        )
    )
    db.flush()


def _record_learning_signals(db: Session, user: User, payload: dict[str, Any]) -> None:
    notes = _dict_list(payload.get("vocabulary_notes"))
    grammar_notes = _dict_list(payload.get("grammar_notes"))
    corrections = _dict_list(payload.get("corrections"))
    if not notes and not grammar_notes and not corrections:
        return
    rating = ReviewRating.AGAIN if corrections or grammar_notes else ReviewRating.HARD
    for index, note in enumerate(notes[:3]):
        term = str(note.get("term") or note.get("hanzi") or "").strip()
        if not term:
            continue
        vocabulary = db.scalar(select(Vocabulary).where(Vocabulary.simplified == term).order_by(Vocabulary.id).limit(1))
        if vocabulary is None:
            continue
        card = enroll_card(
            db,
            user,
            "VOCABULARY",
            vocabulary_id=vocabulary.id,
            content_key=f"vocabulary:{vocabulary.id}",
            content={"hanzi": vocabulary.simplified, "pinyin": vocabulary.pinyin, "meaning": note.get("meaning")},
            source="AI_TUTOR",
        )
        try:
            review_card(
                db,
                user,
                card.id,
                rating,
                idempotency_key=f"ai-tutor:vocab:{user.id}:{card.id}:{index}:{datetime.now(UTC).date().isoformat()}",
                source="AI_TUTOR",
                metadata={"source": "AI_TUTOR", "term": term},
            )
        except ValueError:
            logger.info("ai_tutor_review_skipped", extra={"term": term})
    for index, note in enumerate(grammar_notes[:2]):
        point = str(note.get("point") or note.get("title") or "").strip()
        if not point:
            continue
        grammar = db.scalar(select(GrammarPoint).where(GrammarPoint.title == point).order_by(GrammarPoint.id).limit(1))
        if grammar is None:
            continue
        card = enroll_card(
            db,
            user,
            "GRAMMAR",
            grammar_id=str(grammar.id),
            content_key=f"grammar:{grammar.id}",
            content={"title": grammar.title, "pattern": grammar.pattern},
            source="AI_TUTOR",
        )
        try:
            review_card(
                db,
                user,
                card.id,
                rating,
                idempotency_key=f"ai-tutor:grammar:{user.id}:{card.id}:{index}:{datetime.now(UTC).date().isoformat()}",
                source="AI_TUTOR",
                metadata={"source": "AI_TUTOR", "point": point},
            )
        except ValueError:
            logger.info("ai_tutor_grammar_review_skipped", extra={"point": point})


def _existing_turn(
    db: Session, conversation_id: int, idempotency_key: str
) -> tuple[ConversationMessage, ConversationMessage] | None:
    user_message = db.scalar(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.idempotency_key == idempotency_key,
            ConversationMessage.role == ConversationMessageRole.USER.value,
        )
    )
    if user_message is None:
        return None
    assistant_message = db.scalar(
        select(ConversationMessage)
        .where(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.role == ConversationMessageRole.ASSISTANT.value,
            ConversationMessage.created_at >= user_message.created_at,
        )
        .order_by(ConversationMessage.created_at.asc())
    )
    if assistant_message is None:
        return None
    return user_message, assistant_message


def _history_messages(conversation: Conversation) -> list[dict[str, str]]:
    visible = [
        item
        for item in conversation.messages
        if item.role != ConversationMessageRole.SYSTEM.value
    ]
    recent = visible[-settings.ai_max_history_messages :]
    rows: list[dict[str, str]] = []
    if conversation.summary:
        rows.append({"role": "assistant", "content": f"Earlier practice summary: {conversation.summary}"})
    for item in recent:
        role = "assistant" if item.role == ConversationMessageRole.ASSISTANT.value else "user"
        rows.append({"role": role, "content": item.content})
    return rows


def _conversation_payload(result: AIProviderResult, fallback: str) -> dict[str, Any]:
    payload = dict(result.payload or {})
    message = str(payload.get("message") or payload.get("chinese_text") or fallback)
    chinese = str(payload.get("chinese_text") or message)
    payload["message"] = message
    payload["chinese_text"] = chinese
    payload["pinyin"] = payload.get("pinyin")
    payload["translation"] = payload.get("translation")
    payload["corrections"] = _dict_list(payload.get("corrections"))
    payload["vocabulary_notes"] = _dict_list(payload.get("vocabulary_notes"))
    payload["grammar_notes"] = _dict_list(payload.get("grammar_notes"))
    return payload


def _enforce_rate_limit(db: Session, user_id: int) -> None:
    window_start = datetime.now(UTC) - timedelta(minutes=1)
    count = db.scalar(
        select(func.count(AiUsageEvent.id)).where(
            AiUsageEvent.user_id == user_id,
            AiUsageEvent.created_at >= window_start,
        )
    ) or 0
    if count >= settings.ai_rate_limit_per_minute:
        raise AITutorServiceError(429, USER_FACING_ERRORS["RATE_LIMIT"])


def _validate_input(text: str) -> None:
    if not text:
        raise AITutorServiceError(422, "Message cannot be empty")
    if len(text) > settings.ai_max_input_characters:
        raise AITutorServiceError(422, USER_FACING_ERRORS["INPUT_TOO_LONG"])


def _owned_lesson(db: Session, lesson_id: int | None) -> Lesson | None:
    if not lesson_id:
        return None
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise AITutorServiceError(404, "Lesson not found")
    return lesson


def _owned_course(db: Session, course_id: int | None) -> Course | None:
    if not course_id:
        return None
    course = db.get(Course, course_id)
    if course is None:
        raise AITutorServiceError(404, "Course not found")
    return course


def _default_title(mode: str, scenario_id: str | None, lesson: Lesson | None) -> str:
    if mode == ConversationMode.ROLE_PLAY.value:
        scenario = scenario_by_id(scenario_id)
        return f"Role play · {scenario['title']}" if scenario else "Role play"
    if lesson:
        return lesson.title
    return MODE_TITLES.get(mode, "AI Tutor")


def _public_error(error: AITutorError | None) -> str:
    if error is None:
        return USER_FACING_ERRORS["PROVIDER_ERROR"]
    return USER_FACING_ERRORS.get(error.code, USER_FACING_ERRORS["PROVIDER_ERROR"])


def _token_usage(result: AIProviderResult) -> dict[str, Any]:
    return {
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "provider": result.provider,
        "model": result.model,
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()][:8]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)][:8]


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "yes", "correct"}:
            return True
        if lowered in {"false", "no", "incorrect"}:
            return False
    return bool(value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
