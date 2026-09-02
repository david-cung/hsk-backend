from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _add_column(engine: Engine, table: str, column: str, ddl: str) -> None:
    inspector = inspect(engine)
    columns = {row["name"] for row in inspector.get_columns(table)} if inspector.has_table(table) else set()
    if column in columns:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _create_table(engine: Engine, table: str, ddl: str) -> None:
    inspector = inspect(engine)
    if inspector.has_table(table):
        return
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _add_index(engine: Engine, table: str, index: str, ddl: str) -> None:
    inspector = inspect(engine)
    if not inspector.has_table(table):
        return
    indexes = {row["name"] for row in inspector.get_indexes(table)}
    if index in indexes:
        return
    with engine.begin() as conn:
        conn.execute(text(ddl))


def ensure_phase5_schema(engine: Engine) -> None:
    """Small compatibility migration for deployments that rely on create_all."""
    if engine.dialect.name == "postgresql":
        _add_column(engine, "audio_assets", "storage_key", "storage_key VARCHAR(500) DEFAULT '' NOT NULL")
        _add_column(engine, "audio_assets", "provider", "provider VARCHAR(40) DEFAULT 'tts' NOT NULL")
        _add_column(engine, "audio_assets", "mime_type", "mime_type VARCHAR(120) DEFAULT 'audio/mpeg' NOT NULL")
        _add_column(engine, "audio_assets", "duration_seconds", "duration_seconds DOUBLE PRECISION")
        _add_column(engine, "audio_assets", "language", "language VARCHAR(20) DEFAULT 'zh-CN' NOT NULL")
        _add_column(engine, "audio_assets", "transcript", "transcript TEXT")
        _add_column(engine, "audio_assets", "pinyin", "pinyin TEXT")
        _add_column(engine, "audio_assets", "translation", "translation TEXT")
        _add_column(engine, "audio_assets", "status", "status VARCHAR(40) DEFAULT 'READY' NOT NULL")
        _add_column(engine, "audio_assets", "metadata", "metadata JSONB DEFAULT '{}'::jsonb NOT NULL")
        _add_column(engine, "audio_assets", "created_at", "created_at TIMESTAMPTZ DEFAULT now() NOT NULL")
        _add_column(engine, "audio_assets", "updated_at", "updated_at TIMESTAMPTZ DEFAULT now() NOT NULL")
        _add_column(engine, "users", "is_admin", "is_admin BOOLEAN DEFAULT FALSE NOT NULL")
        _add_column(engine, "questions", "exercise_id", "exercise_id INTEGER")
        _add_column(engine, "questions", "instruction", "instruction TEXT")
        _add_column(engine, "questions", "difficulty", "difficulty INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "questions", "points", "points INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "questions", "config", "config JSONB DEFAULT '{}'::jsonb NOT NULL")
        _add_column(engine, "questions", "reference_type", "reference_type VARCHAR(40)")
        _add_column(engine, "questions", "reference_id", "reference_id VARCHAR(120)")
        _add_column(engine, "questions", "is_archived", "is_archived BOOLEAN DEFAULT FALSE NOT NULL")
        _add_column(engine, "answer_attempts", "metadata", "metadata JSONB DEFAULT '{}'::jsonb NOT NULL")
        _add_column(engine, "profiles", "longest_streak_days", "longest_streak_days INTEGER DEFAULT 0 NOT NULL")
        _add_column(engine, "profiles", "last_active_date", "last_active_date DATE")
        _add_column(engine, "profiles", "timezone", "timezone VARCHAR(80) DEFAULT 'Asia/Ho_Chi_Minh' NOT NULL")
        _add_column(engine, "profiles", "daily_new_cards_limit", "daily_new_cards_limit INTEGER DEFAULT 10 NOT NULL")
        _add_column(engine, "profiles", "daily_review_cards_limit", "daily_review_cards_limit INTEGER DEFAULT 50 NOT NULL")
        _add_column(engine, "mock_tests", "description", "description TEXT")
        _add_column(engine, "mock_tests", "exam_type", "exam_type VARCHAR(40) DEFAULT 'MOCK' NOT NULL")
        _add_column(engine, "mock_tests", "status", "status VARCHAR(40) DEFAULT 'PUBLISHED' NOT NULL")
        _add_column(engine, "mock_tests", "version", "version INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "mock_tests", "blueprint", "blueprint JSONB DEFAULT '{}'::jsonb NOT NULL")
        _add_column(engine, "mock_tests", "scoring_config", "scoring_config JSONB DEFAULT '{}'::jsonb NOT NULL")
        _add_column(engine, "mock_tests", "instructions", "instructions TEXT")
        _add_column(engine, "mock_tests", "published_at", "published_at TIMESTAMPTZ")
        _add_column(engine, "mock_tests", "archived_at", "archived_at TIMESTAMPTZ")
        _add_column(engine, "lesson_progress", "speaking_attempts", "speaking_attempts INTEGER DEFAULT 0 NOT NULL")
        _add_column(
            engine,
            "lesson_progress",
            "speaking_acceptable_attempts",
            "speaking_acceptable_attempts INTEGER DEFAULT 0 NOT NULL",
        )
        _add_column(engine, "lesson_progress", "pronunciation_score_avg", "pronunciation_score_avg DOUBLE PRECISION")
        _add_column(engine, "lesson_progress", "last_speaking_practice", "last_speaking_practice TIMESTAMPTZ")
        _create_table(
            engine,
            "speech_recordings",
            """
            CREATE TABLE speech_recordings (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                storage_provider VARCHAR(40) DEFAULT 'mock' NOT NULL,
                storage_key VARCHAR(500) NOT NULL,
                original_filename VARCHAR(255),
                mime_type VARCHAR(120) NOT NULL,
                extension VARCHAR(20) NOT NULL,
                size_bytes INTEGER,
                duration_seconds DOUBLE PRECISION,
                language VARCHAR(20) DEFAULT 'zh-CN' NOT NULL,
                status VARCHAR(40) DEFAULT 'UPLOAD_AUTHORIZED' NOT NULL,
                upload_expires_at TIMESTAMPTZ NOT NULL,
                uploaded_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                CONSTRAINT uq_speech_recordings_storage_key UNIQUE (storage_provider, storage_key)
            )
            """,
        )
        _create_table(
            engine,
            "speaking_attempts",
            """
            CREATE TABLE speaking_attempts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                practice_session_id INTEGER NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
                answer_attempt_id INTEGER NOT NULL REFERENCES answer_attempts(id) ON DELETE CASCADE,
                recording_id INTEGER NOT NULL REFERENCES speech_recordings(id) ON DELETE RESTRICT,
                provider VARCHAR(40) NOT NULL,
                provider_model_version VARCHAR(120),
                recognized_text TEXT,
                confidence DOUBLE PRECISION,
                pronunciation_score DOUBLE PRECISION,
                accuracy_score DOUBLE PRECISION,
                fluency_score DOUBLE PRECISION,
                completeness_score DOUBLE PRECISION,
                word_feedback JSONB DEFAULT '[]'::jsonb NOT NULL,
                tone_feedback JSONB,
                feedback_label VARCHAR(80),
                processing_status VARCHAR(40) DEFAULT 'PENDING' NOT NULL,
                error_code VARCHAR(80),
                error_message TEXT,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                completed_at TIMESTAMPTZ,
                CONSTRAINT uq_speaking_attempts_answer_attempt UNIQUE (answer_attempt_id)
            )
            """,
        )
        _add_index(
            engine,
            "answer_attempts",
            "ix_answer_attempts_user_attempted",
            "CREATE INDEX ix_answer_attempts_user_attempted ON answer_attempts (user_id, attempted_at)",
        )
        _add_index(
            engine,
            "practice_sessions",
            "ix_practice_sessions_user_started",
            "CREATE INDEX ix_practice_sessions_user_started ON practice_sessions (user_id, started_at)",
        )
        _add_index(
            engine,
            "practice_sessions",
            "ix_practice_sessions_user_completed",
            "CREATE INDEX ix_practice_sessions_user_completed ON practice_sessions (user_id, completed_at)",
        )
        _add_index(
            engine,
            "quiz_attempts",
            "ix_quiz_attempts_user_finished",
            "CREATE INDEX ix_quiz_attempts_user_finished ON quiz_attempts (user_id, finished_at)",
        )
        _add_index(
            engine,
            "lesson_progress",
            "ix_lesson_progress_user_updated",
            "CREATE INDEX ix_lesson_progress_user_updated ON lesson_progress (user_id, updated_at)",
        )
        _create_table(
            engine,
            "review_cards",
            """
            CREATE TABLE review_cards (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                card_type VARCHAR(40) NOT NULL,
                content_key VARCHAR(180) NOT NULL,
                vocabulary_id INTEGER,
                grammar_id VARCHAR(180),
                state VARCHAR(40) DEFAULT 'NEW' NOT NULL,
                due_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                last_reviewed_at TIMESTAMPTZ,
                reps INTEGER DEFAULT 0 NOT NULL,
                lapses INTEGER DEFAULT 0 NOT NULL,
                stability DOUBLE PRECISION,
                difficulty DOUBLE PRECISION,
                interval_days DOUBLE PRECISION DEFAULT 0 NOT NULL,
                scheduler_version VARCHAR(40) DEFAULT 'fsrs-5-default' NOT NULL,
                content_snapshot JSONB DEFAULT '{}'::jsonb NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                CONSTRAINT ck_review_cards_one_content_ref CHECK (
                    (card_type = 'VOCABULARY' AND grammar_id IS NULL)
                    OR (card_type = 'GRAMMAR' AND grammar_id IS NOT NULL AND vocabulary_id IS NULL)
                ),
                CONSTRAINT uq_review_cards_user_content UNIQUE (user_id, card_type, content_key)
            )
            """,
        )
        _create_table(
            engine,
            "review_history",
            """
            CREATE TABLE review_history (
                id SERIAL PRIMARY KEY,
                card_id INTEGER NOT NULL REFERENCES review_cards(id) ON DELETE RESTRICT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                rating VARCHAR(20) NOT NULL,
                reviewed_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                previous_state VARCHAR(40) NOT NULL,
                new_state VARCHAR(40) NOT NULL,
                previous_due_at TIMESTAMPTZ,
                new_due_at TIMESTAMPTZ NOT NULL,
                previous_stability DOUBLE PRECISION,
                new_stability DOUBLE PRECISION,
                previous_difficulty DOUBLE PRECISION,
                new_difficulty DOUBLE PRECISION,
                source VARCHAR(40) NOT NULL,
                idempotency_key VARCHAR(160) NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                CONSTRAINT uq_review_history_user_key UNIQUE (user_id, idempotency_key)
            )
            """,
        )
        _add_index(engine, "review_cards", "ix_review_cards_user_due", "CREATE INDEX ix_review_cards_user_due ON review_cards (user_id, due_at)")
        _add_index(engine, "review_cards", "ix_review_cards_user_type", "CREATE INDEX ix_review_cards_user_type ON review_cards (user_id, card_type)")
        _add_index(engine, "review_cards", "ix_review_cards_vocabulary", "CREATE INDEX ix_review_cards_vocabulary ON review_cards (vocabulary_id)")
        _add_index(engine, "review_cards", "ix_review_cards_grammar", "CREATE INDEX ix_review_cards_grammar ON review_cards (grammar_id)")
        _add_index(engine, "review_history", "ix_review_history_card_reviewed", "CREATE INDEX ix_review_history_card_reviewed ON review_history (card_id, reviewed_at)")
        _add_index(engine, "review_history", "ix_review_history_user_reviewed", "CREATE INDEX ix_review_history_user_reviewed ON review_history (user_id, reviewed_at)")
        _create_table(
            engine,
            "exam_attempts",
            """
            CREATE TABLE exam_attempts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                exam_id INTEGER NOT NULL REFERENCES mock_tests(id) ON DELETE RESTRICT,
                exam_version INTEGER NOT NULL,
                status VARCHAR(40) DEFAULT 'IN_PROGRESS' NOT NULL,
                started_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                submitted_at TIMESTAMPTZ,
                expires_at TIMESTAMPTZ NOT NULL,
                score DOUBLE PRECISION,
                percentage DOUBLE PRECISION,
                passed BOOLEAN,
                random_seed INTEGER NOT NULL,
                current_section VARCHAR(40),
                question_snapshot JSONB DEFAULT '{}'::jsonb NOT NULL,
                section_results JSONB DEFAULT '[]'::jsonb NOT NULL,
                result_summary JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT now() NOT NULL
            )
            """,
        )
        _create_table(
            engine,
            "exam_question_results",
            """
            CREATE TABLE exam_question_results (
                id SERIAL PRIMARY KEY,
                exam_attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
                section VARCHAR(40) NOT NULL,
                answer JSONB,
                correct BOOLEAN,
                points DOUBLE PRECISION DEFAULT 0 NOT NULL,
                max_points DOUBLE PRECISION DEFAULT 1 NOT NULL,
                answered_at TIMESTAMPTZ,
                evaluated_at TIMESTAMPTZ,
                metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
                CONSTRAINT uq_exam_question_results_attempt_question UNIQUE (exam_attempt_id, question_id)
            )
            """,
        )
        _add_index(engine, "exam_attempts", "ix_exam_attempts_user_status", "CREATE INDEX ix_exam_attempts_user_status ON exam_attempts (user_id, status)")
        _add_index(engine, "exam_attempts", "ix_exam_attempts_user_created", "CREATE INDEX ix_exam_attempts_user_created ON exam_attempts (user_id, created_at)")
        _add_index(engine, "exam_attempts", "ix_exam_attempts_exam_user", "CREATE INDEX ix_exam_attempts_exam_user ON exam_attempts (exam_id, user_id)")
        _add_index(engine, "exam_question_results", "ix_exam_question_results_attempt", "CREATE INDEX ix_exam_question_results_attempt ON exam_question_results (exam_attempt_id)")
        _add_index(engine, "exam_question_results", "ix_exam_question_results_question", "CREATE INDEX ix_exam_question_results_question ON exam_question_results (question_id)")
    elif engine.dialect.name == "sqlite":
        _add_column(engine, "audio_assets", "storage_key", "storage_key VARCHAR(500) DEFAULT '' NOT NULL")
        _add_column(engine, "audio_assets", "provider", "provider VARCHAR(40) DEFAULT 'tts' NOT NULL")
        _add_column(engine, "audio_assets", "mime_type", "mime_type VARCHAR(120) DEFAULT 'audio/mpeg' NOT NULL")
        _add_column(engine, "audio_assets", "duration_seconds", "duration_seconds FLOAT")
        _add_column(engine, "audio_assets", "language", "language VARCHAR(20) DEFAULT 'zh-CN' NOT NULL")
        _add_column(engine, "audio_assets", "transcript", "transcript TEXT")
        _add_column(engine, "audio_assets", "pinyin", "pinyin TEXT")
        _add_column(engine, "audio_assets", "translation", "translation TEXT")
        _add_column(engine, "audio_assets", "status", "status VARCHAR(40) DEFAULT 'READY' NOT NULL")
        _add_column(engine, "audio_assets", "metadata", "metadata JSON DEFAULT '{}' NOT NULL")
        _add_column(engine, "audio_assets", "created_at", "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL")
        _add_column(engine, "audio_assets", "updated_at", "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL")
        _add_column(engine, "users", "is_admin", "is_admin BOOLEAN DEFAULT 0 NOT NULL")
        _add_column(engine, "questions", "exercise_id", "exercise_id INTEGER")
        _add_column(engine, "questions", "instruction", "instruction TEXT")
        _add_column(engine, "questions", "difficulty", "difficulty INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "questions", "points", "points INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "questions", "config", "config JSON DEFAULT '{}' NOT NULL")
        _add_column(engine, "questions", "reference_type", "reference_type VARCHAR(40)")
        _add_column(engine, "questions", "reference_id", "reference_id VARCHAR(120)")
        _add_column(engine, "questions", "is_archived", "is_archived BOOLEAN DEFAULT 0 NOT NULL")
        _add_column(engine, "answer_attempts", "metadata", "metadata JSON DEFAULT '{}' NOT NULL")
        _add_column(engine, "profiles", "longest_streak_days", "longest_streak_days INTEGER DEFAULT 0 NOT NULL")
        _add_column(engine, "profiles", "last_active_date", "last_active_date DATE")
        _add_column(engine, "profiles", "timezone", "timezone VARCHAR(80) DEFAULT 'Asia/Ho_Chi_Minh' NOT NULL")
        _add_column(engine, "profiles", "daily_new_cards_limit", "daily_new_cards_limit INTEGER DEFAULT 10 NOT NULL")
        _add_column(engine, "profiles", "daily_review_cards_limit", "daily_review_cards_limit INTEGER DEFAULT 50 NOT NULL")
        _add_column(engine, "mock_tests", "description", "description TEXT")
        _add_column(engine, "mock_tests", "exam_type", "exam_type VARCHAR(40) DEFAULT 'MOCK' NOT NULL")
        _add_column(engine, "mock_tests", "status", "status VARCHAR(40) DEFAULT 'PUBLISHED' NOT NULL")
        _add_column(engine, "mock_tests", "version", "version INTEGER DEFAULT 1 NOT NULL")
        _add_column(engine, "mock_tests", "blueprint", "blueprint JSON DEFAULT '{}' NOT NULL")
        _add_column(engine, "mock_tests", "scoring_config", "scoring_config JSON DEFAULT '{}' NOT NULL")
        _add_column(engine, "mock_tests", "instructions", "instructions TEXT")
        _add_column(engine, "mock_tests", "published_at", "published_at DATETIME")
        _add_column(engine, "mock_tests", "archived_at", "archived_at DATETIME")
        _add_column(engine, "lesson_progress", "speaking_attempts", "speaking_attempts INTEGER DEFAULT 0 NOT NULL")
        _add_column(
            engine,
            "lesson_progress",
            "speaking_acceptable_attempts",
            "speaking_acceptable_attempts INTEGER DEFAULT 0 NOT NULL",
        )
        _add_column(engine, "lesson_progress", "pronunciation_score_avg", "pronunciation_score_avg FLOAT")
        _add_column(engine, "lesson_progress", "last_speaking_practice", "last_speaking_practice DATETIME")
        _create_table(
            engine,
            "speech_recordings",
            """
            CREATE TABLE speech_recordings (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                storage_provider VARCHAR(40) DEFAULT 'mock' NOT NULL,
                storage_key VARCHAR(500) NOT NULL,
                original_filename VARCHAR(255),
                mime_type VARCHAR(120) NOT NULL,
                extension VARCHAR(20) NOT NULL,
                size_bytes INTEGER,
                duration_seconds FLOAT,
                language VARCHAR(20) DEFAULT 'zh-CN' NOT NULL,
                status VARCHAR(40) DEFAULT 'UPLOAD_AUTHORIZED' NOT NULL,
                upload_expires_at DATETIME NOT NULL,
                uploaded_at DATETIME,
                expires_at DATETIME,
                metadata JSON DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT uq_speech_recordings_storage_key UNIQUE (storage_provider, storage_key)
            )
            """,
        )
        _add_index(
            engine,
            "answer_attempts",
            "ix_answer_attempts_user_attempted",
            "CREATE INDEX ix_answer_attempts_user_attempted ON answer_attempts (user_id, attempted_at)",
        )
        _add_index(
            engine,
            "practice_sessions",
            "ix_practice_sessions_user_started",
            "CREATE INDEX ix_practice_sessions_user_started ON practice_sessions (user_id, started_at)",
        )
        _add_index(
            engine,
            "practice_sessions",
            "ix_practice_sessions_user_completed",
            "CREATE INDEX ix_practice_sessions_user_completed ON practice_sessions (user_id, completed_at)",
        )
        _add_index(
            engine,
            "quiz_attempts",
            "ix_quiz_attempts_user_finished",
            "CREATE INDEX ix_quiz_attempts_user_finished ON quiz_attempts (user_id, finished_at)",
        )
        _add_index(
            engine,
            "lesson_progress",
            "ix_lesson_progress_user_updated",
            "CREATE INDEX ix_lesson_progress_user_updated ON lesson_progress (user_id, updated_at)",
        )
        _create_table(
            engine,
            "speaking_attempts",
            """
            CREATE TABLE speaking_attempts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                practice_session_id INTEGER NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
                answer_attempt_id INTEGER NOT NULL REFERENCES answer_attempts(id) ON DELETE CASCADE,
                recording_id INTEGER NOT NULL REFERENCES speech_recordings(id) ON DELETE RESTRICT,
                provider VARCHAR(40) NOT NULL,
                provider_model_version VARCHAR(120),
                recognized_text TEXT,
                confidence FLOAT,
                pronunciation_score FLOAT,
                accuracy_score FLOAT,
                fluency_score FLOAT,
                completeness_score FLOAT,
                word_feedback JSON DEFAULT '[]' NOT NULL,
                tone_feedback JSON,
                feedback_label VARCHAR(80),
                processing_status VARCHAR(40) DEFAULT 'PENDING' NOT NULL,
                error_code VARCHAR(80),
                error_message TEXT,
                metadata JSON DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                completed_at DATETIME,
                CONSTRAINT uq_speaking_attempts_answer_attempt UNIQUE (answer_attempt_id)
            )
            """,
        )
        _create_table(
            engine,
            "review_cards",
            """
            CREATE TABLE review_cards (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                card_type VARCHAR(40) NOT NULL,
                content_key VARCHAR(180) NOT NULL,
                vocabulary_id INTEGER,
                grammar_id VARCHAR(180),
                state VARCHAR(40) DEFAULT 'NEW' NOT NULL,
                due_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                last_reviewed_at DATETIME,
                reps INTEGER DEFAULT 0 NOT NULL,
                lapses INTEGER DEFAULT 0 NOT NULL,
                stability FLOAT,
                difficulty FLOAT,
                interval_days FLOAT DEFAULT 0 NOT NULL,
                scheduler_version VARCHAR(40) DEFAULT 'fsrs-5-default' NOT NULL,
                content_snapshot JSON DEFAULT '{}' NOT NULL,
                metadata JSON DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT ck_review_cards_one_content_ref CHECK (
                    (card_type = 'VOCABULARY' AND grammar_id IS NULL)
                    OR (card_type = 'GRAMMAR' AND grammar_id IS NOT NULL AND vocabulary_id IS NULL)
                ),
                CONSTRAINT uq_review_cards_user_content UNIQUE (user_id, card_type, content_key)
            )
            """,
        )
        _create_table(
            engine,
            "review_history",
            """
            CREATE TABLE review_history (
                id INTEGER PRIMARY KEY,
                card_id INTEGER NOT NULL REFERENCES review_cards(id) ON DELETE RESTRICT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                rating VARCHAR(20) NOT NULL,
                reviewed_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                previous_state VARCHAR(40) NOT NULL,
                new_state VARCHAR(40) NOT NULL,
                previous_due_at DATETIME,
                new_due_at DATETIME NOT NULL,
                previous_stability FLOAT,
                new_stability FLOAT,
                previous_difficulty FLOAT,
                new_difficulty FLOAT,
                source VARCHAR(40) NOT NULL,
                idempotency_key VARCHAR(160) NOT NULL,
                metadata JSON DEFAULT '{}' NOT NULL,
                CONSTRAINT uq_review_history_user_key UNIQUE (user_id, idempotency_key)
            )
            """,
        )
        _add_index(engine, "review_cards", "ix_review_cards_user_due", "CREATE INDEX ix_review_cards_user_due ON review_cards (user_id, due_at)")
        _add_index(engine, "review_cards", "ix_review_cards_user_type", "CREATE INDEX ix_review_cards_user_type ON review_cards (user_id, card_type)")
        _add_index(engine, "review_cards", "ix_review_cards_vocabulary", "CREATE INDEX ix_review_cards_vocabulary ON review_cards (vocabulary_id)")
        _add_index(engine, "review_cards", "ix_review_cards_grammar", "CREATE INDEX ix_review_cards_grammar ON review_cards (grammar_id)")
        _add_index(engine, "review_history", "ix_review_history_card_reviewed", "CREATE INDEX ix_review_history_card_reviewed ON review_history (card_id, reviewed_at)")
        _add_index(engine, "review_history", "ix_review_history_user_reviewed", "CREATE INDEX ix_review_history_user_reviewed ON review_history (user_id, reviewed_at)")
        _create_table(
            engine,
            "exam_attempts",
            """
            CREATE TABLE exam_attempts (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                exam_id INTEGER NOT NULL REFERENCES mock_tests(id) ON DELETE RESTRICT,
                exam_version INTEGER NOT NULL,
                status VARCHAR(40) DEFAULT 'IN_PROGRESS' NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                submitted_at DATETIME,
                expires_at DATETIME NOT NULL,
                score FLOAT,
                percentage FLOAT,
                passed BOOLEAN,
                random_seed INTEGER NOT NULL,
                current_section VARCHAR(40),
                question_snapshot JSON DEFAULT '{}' NOT NULL,
                section_results JSON DEFAULT '[]' NOT NULL,
                result_summary JSON DEFAULT '{}' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
            )
            """,
        )
        _create_table(
            engine,
            "exam_question_results",
            """
            CREATE TABLE exam_question_results (
                id INTEGER PRIMARY KEY,
                exam_attempt_id INTEGER NOT NULL REFERENCES exam_attempts(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE RESTRICT,
                section VARCHAR(40) NOT NULL,
                answer JSON,
                correct BOOLEAN,
                points FLOAT DEFAULT 0 NOT NULL,
                max_points FLOAT DEFAULT 1 NOT NULL,
                answered_at DATETIME,
                evaluated_at DATETIME,
                metadata JSON DEFAULT '{}' NOT NULL,
                CONSTRAINT uq_exam_question_results_attempt_question UNIQUE (exam_attempt_id, question_id)
            )
            """,
        )
        _add_index(engine, "exam_attempts", "ix_exam_attempts_user_status", "CREATE INDEX ix_exam_attempts_user_status ON exam_attempts (user_id, status)")
        _add_index(engine, "exam_attempts", "ix_exam_attempts_user_created", "CREATE INDEX ix_exam_attempts_user_created ON exam_attempts (user_id, created_at)")
        _add_index(engine, "exam_attempts", "ix_exam_attempts_exam_user", "CREATE INDEX ix_exam_attempts_exam_user ON exam_attempts (exam_id, user_id)")
        _add_index(engine, "exam_question_results", "ix_exam_question_results_attempt", "CREATE INDEX ix_exam_question_results_attempt ON exam_question_results (exam_attempt_id)")
        _add_index(engine, "exam_question_results", "ix_exam_question_results_question", "CREATE INDEX ix_exam_question_results_question ON exam_question_results (question_id)")
