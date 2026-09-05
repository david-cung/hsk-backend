# HSK Backend

FastAPI + PostgreSQL API for the HSK Chinese Master mobile app.

## Run With Docker

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432`

The API runs Alembic migrations before startup, then idempotently seeds starter HSK content.

## Database Migrations

```bash
# Host development database
DATABASE_URL=postgresql+psycopg://hsk:hsk@localhost:5432/hsk \
  .venv/bin/alembic upgrade head
```

Existing databases created before Alembic must be stamped at the baseline once,
then upgraded:

```bash
DATABASE_URL=postgresql+psycopg://hsk:hsk@localhost:5432/hsk \
  .venv/bin/alembic stamp 9d89e918ffee
DATABASE_URL=postgresql+psycopg://hsk:hsk@localhost:5432/hsk \
  .venv/bin/alembic upgrade head
```

Docker Compose performs `alembic upgrade head` automatically.

## Authentication Configuration

Required production environment variables:

- `JWT_SECRET`: strong random signing secret (never use the development default).
- `GOOGLE_CLIENT_ID`: Google OAuth **Web client ID** used to validate ID-token audiences.
- `DATABASE_URL`: PostgreSQL connection URL.

Optional:

- `ACCESS_TOKEN_EXPIRE_MINUTES` (default: `45`)
- `REFRESH_TOKEN_EXPIRE_DAYS` (default: `30`)
- `PASSWORD_RESET_EXPIRE_MINUTES` (default: `30`)
- `PASSWORD_RESET_URL` (default: `hsk://reset-password`)

AI tutor (Phase 12) — backend-only, never sent to the mobile app:

- `AI_PROVIDER` (default: `mock`; use `openrouter` in production)
- `AI_MODEL` (default: `openai/gpt-4o-mini`)
- `AI_API_KEY` (required when `AI_PROVIDER=openrouter`)
- `AI_BASE_URL` (default: `https://openrouter.ai/api/v1`)
- `AI_MAX_TOKENS` (default: `800`)
- `AI_TEMPERATURE` (default: `0.7`)
- `AI_TIMEOUT` (default: `30`)
- `AI_MAX_HISTORY_MESSAGES` (default: `12`)
- `AI_MAX_INPUT_CHARACTERS` (default: `2000`)
- `AI_RATE_LIMIT_PER_MINUTE` (default: `20`)
- `AI_TUTOR_PROMPT_VERSION` (default: `v1`)
- `AI_WRITING_FEEDBACK_ENABLED` (default: `false`; supplementary GUIDED_WRITING comments only)

Password-reset delivery currently uses the development `LoggingEmailSender`.
Replace the `EmailSender` dependency with a production email-provider adapter
before deploying password reset publicly.

## Mobile App Contract

Implemented endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/google`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `PATCH /api/v1/auth/password`
- `GET /api/v1/auth/me`
- `DELETE /api/v1/auth/me`
- `GET /api/v1/auth/me/profile`
- `PATCH /api/v1/profile`
- `GET /api/v1/content/levels`
- `GET /api/v1/content/levels/{level_id}/lessons`
- `GET /api/v1/content/lessons/{lesson_id}`
- `GET /api/v1/content/lessons/{lesson_id}/questions`
- `POST /api/v1/quiz/lessons/{lesson_id}/submit`
- `GET /api/v1/progress/dashboard`
- `GET /api/v1/learning/saved-words`
- `POST /api/v1/learning/saved-words`
- `DELETE /api/v1/learning/saved-words/{word_id}`
- `GET /api/v1/learning/achievements`
- `GET /api/v1/learning/mock-tests`

Phase 4 normalized content endpoints:

- `GET /api/v1/hsk/levels`
- `GET /api/v1/courses?hsk_level=1`
- `GET /api/v1/courses/{course_id}/lessons`
- `GET /api/v1/lessons/{lesson_id}`
- `GET /api/v1/vocabulary` and `GET /api/v1/vocabulary/{id}`
- `POST|DELETE /api/v1/vocabulary/{id}/favorite`
- `GET /api/v1/vocabulary/favorites`
- `GET /api/v1/lessons/{lesson_id}/grammar`
- `GET /api/v1/grammar/{id}`
- Lesson, vocabulary, and grammar progress-hook endpoints documented in OpenAPI.
- Admin CRUD under `/api/v1/admin/content/*`.

Legacy `/api/v1/content/*` routes remain available during the mobile transition.

Phase 5 practice endpoints:

- `GET /api/v1/practice/lessons/{lesson_id}`
- `POST /api/v1/practice/sessions`
- `GET /api/v1/practice/sessions/{session_id}`
- `POST /api/v1/practice/sessions/{session_id}/answers`
- `POST /api/v1/practice/sessions/{session_id}/complete`
- `GET /api/v1/practice/sessions/{session_id}/results`
- Admin exercise/question management under `/api/v1/admin/exercises` and
  `/api/v1/admin/questions`.

Practice questions and their validated configurations are the canonical source
for evaluation. The server removes answer keys before returning active-session
questions. Legacy `lesson.content.practice_exercises` remains unchanged and is
normalized idempotently for compatibility; legacy quiz routes continue to use
the existing `Question` rows during the mobile transition.

Phase 12 AI tutor endpoints (mobile never calls the AI provider directly):

- `GET /api/v1/ai/scenarios`
- `GET /api/v1/ai/conversations`
- `POST /api/v1/ai/conversations`
- `GET /api/v1/ai/conversations/{id}`
- `DELETE /api/v1/ai/conversations/{id}`
- `POST /api/v1/ai/conversations/{id}/messages`
- `POST /api/v1/ai/sentence-check`
- `POST /api/v1/ai/grammar-explain`
- `POST /api/v1/ai/writing-feedback`

## Content Import

Admins can import `hsk_levels`, `courses`, `lessons`, `vocabulary`, `grammar`,
`example_sentences`, and nested `exercises`/questions through
`POST /api/v1/admin/content/imports`.
The request accepts JSON records or a CSV string:

```json
{
  "entity_type": "vocabulary",
  "source_format": "json",
  "data": {
    "records": [
      {
        "hsk_level": 1,
        "simplified": "你好",
        "pinyin": "ni3 hao3",
        "meaning_translations": {"en": "hello", "vi": "xin chào"}
      }
    ]
  }
}
```

See `examples/content-import/` for complete JSON and CSV examples. Imports
validate the full input first, use natural-key upserts, and roll back content
changes if any record fails.

Kafka is not included yet because the current product flow does not need asynchronous processing.

## Tests

Tests require an isolated PostgreSQL database:

```bash
createdb hsk_test
PYTHONPATH=. TEST_DATABASE_URL=postgresql+psycopg://hsk:hsk@localhost:5432/hsk_test \
  .venv/bin/pytest -q
```
