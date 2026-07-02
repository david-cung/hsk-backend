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

The API creates tables and seeds starter HSK content automatically when the database is empty.

## Mobile App Contract

Implemented endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
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

Kafka is not included yet because the current product flow does not need asynchronous processing.
