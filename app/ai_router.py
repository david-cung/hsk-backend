from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.ai_service import (
    AITutorServiceError,
    check_sentence,
    conversation_to_out,
    create_conversation,
    delete_conversation,
    explain_grammar,
    get_conversation,
    list_conversations,
    list_scenarios,
    send_message,
    writing_feedback,
)
from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.skill_schemas import (
    ConversationCreateIn,
    ConversationListOut,
    ConversationMessageIn,
    ConversationMessageResultOut,
    ConversationOut,
    GrammarExplainIn,
    GrammarExplainOut,
    RolePlayScenarioOut,
    SentenceCheckIn,
    SentenceCheckOut,
    WritingFeedbackIn,
    WritingFeedbackOut,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai-tutor"])


def _raise(exc: AITutorServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/scenarios", response_model=list[RolePlayScenarioOut])
def scenarios(user: User = Depends(get_current_user)) -> list[RolePlayScenarioOut]:
    _ = user
    return [RolePlayScenarioOut.model_validate(item) for item in list_scenarios()]


@router.get("/conversations", response_model=ConversationListOut)
def conversations(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationListOut:
    return list_conversations(db, user, limit=limit, offset=offset)


@router.post("/conversations", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: ConversationCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationOut:
    try:
        conversation = create_conversation(
            db,
            user,
            mode=payload.mode,
            lesson_id=payload.lesson_id,
            course_id=payload.course_id,
            hsk_level=payload.hsk_level,
            scenario_id=payload.scenario_id,
            explanation_language=payload.explanation_language,
            title=payload.title,
        )
    except AITutorServiceError as exc:
        _raise(exc)
        raise
    return conversation_to_out(conversation, include_messages=False)


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def detail(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationOut:
    try:
        conversation = get_conversation(db, user, conversation_id)
    except AITutorServiceError as exc:
        _raise(exc)
        raise
    return conversation_to_out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        delete_conversation(db, user, conversation_id)
    except AITutorServiceError as exc:
        _raise(exc)
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationMessageResultOut,
)
def messages(
    conversation_id: int,
    payload: ConversationMessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConversationMessageResultOut:
    try:
        return send_message(
            db,
            user,
            conversation_id,
            content=payload.content,
            action=payload.action,
            idempotency_key=payload.idempotency_key,
        )
    except AITutorServiceError as exc:
        _raise(exc)
        raise


@router.post("/sentence-check", response_model=SentenceCheckOut)
def sentence_check(
    payload: SentenceCheckIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SentenceCheckOut:
    try:
        return check_sentence(db, user, sentence=payload.sentence, lesson_id=payload.lesson_id)
    except AITutorServiceError as exc:
        _raise(exc)
        raise


@router.post("/grammar-explain", response_model=GrammarExplainOut)
def grammar_explain(
    payload: GrammarExplainIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GrammarExplainOut:
    try:
        return explain_grammar(
            db,
            user,
            grammar_point=payload.grammar_point,
            sentence=payload.sentence,
            lesson_id=payload.lesson_id,
        )
    except AITutorServiceError as exc:
        _raise(exc)
        raise


@router.post("/writing-feedback", response_model=WritingFeedbackOut)
def writing_feedback_endpoint(
    payload: WritingFeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WritingFeedbackOut:
    try:
        return writing_feedback(
            db,
            user,
            answer=payload.answer,
            prompt=payload.prompt,
            lesson_id=payload.lesson_id,
        )
    except AITutorServiceError as exc:
        _raise(exc)
        raise
