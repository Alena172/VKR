"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-02-19 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("cefr_level", sa.String(length=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "user_contexts",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cefr_level", sa.String(length=2), nullable=False),
        sa.Column("goals", sa.Text(), nullable=False),
        sa.Column("difficult_words", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "word_progress",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(length=200), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("correct_streak", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(), nullable=False),
        sa.Column("next_review_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "word", name="uq_word_progress_user_word"),
    )
    op.create_index(op.f("ix_word_progress_id"), "word_progress", ["id"], unique=False)
    op.create_index(op.f("ix_word_progress_user_id"), "word_progress", ["user_id"], unique=False)
    op.create_index(op.f("ix_word_progress_word"), "word_progress", ["word"], unique=False)
    op.create_index(op.f("ix_word_progress_next_review_at"), "word_progress", ["next_review_at"], unique=False)

    op.create_table(
        "vocabulary_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("english_lemma", sa.String(length=200), nullable=False),
        sa.Column("russian_translation", sa.String(length=200), nullable=False),
        sa.Column("source_sentence", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_vocabulary_items_id"), "vocabulary_items", ["id"], unique=False)
    op.create_index(op.f("ix_vocabulary_items_user_id"), "vocabulary_items", ["user_id"], unique=False)
    op.create_index(op.f("ix_vocabulary_items_english_lemma"), "vocabulary_items", ["english_lemma"], unique=False)

    op.create_table(
        "capture_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("source_sentence", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_capture_items_id"), "capture_items", ["id"], unique=False)
    op.create_index(op.f("ix_capture_items_user_id"), "capture_items", ["user_id"], unique=False)

    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("correct", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_sessions_id"), "learning_sessions", ["id"], unique=False)
    op.create_index(op.f("ix_learning_sessions_user_id"), "learning_sessions", ["user_id"], unique=False)

    op.create_table(
        "learning_session_answers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("expected_answer", sa.String(length=1000), nullable=True),
        sa.Column("user_answer", sa.String(length=1000), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("explanation_ru", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_session_answers_id"), "learning_session_answers", ["id"], unique=False)
    op.create_index(
        op.f("ix_learning_session_answers_session_id"),
        "learning_session_answers",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_session_answers_session_id"), table_name="learning_session_answers")
    op.drop_index(op.f("ix_learning_session_answers_id"), table_name="learning_session_answers")
    op.drop_table("learning_session_answers")

    op.drop_index(op.f("ix_learning_sessions_user_id"), table_name="learning_sessions")
    op.drop_index(op.f("ix_learning_sessions_id"), table_name="learning_sessions")
    op.drop_table("learning_sessions")

    op.drop_index(op.f("ix_capture_items_user_id"), table_name="capture_items")
    op.drop_index(op.f("ix_capture_items_id"), table_name="capture_items")
    op.drop_table("capture_items")

    op.drop_index(op.f("ix_vocabulary_items_english_lemma"), table_name="vocabulary_items")
    op.drop_index(op.f("ix_vocabulary_items_user_id"), table_name="vocabulary_items")
    op.drop_index(op.f("ix_vocabulary_items_id"), table_name="vocabulary_items")
    op.drop_table("vocabulary_items")

    op.drop_index(op.f("ix_word_progress_next_review_at"), table_name="word_progress")
    op.drop_index(op.f("ix_word_progress_word"), table_name="word_progress")
    op.drop_index(op.f("ix_word_progress_user_id"), table_name="word_progress")
    op.drop_index(op.f("ix_word_progress_id"), table_name="word_progress")
    op.drop_table("word_progress")

    op.drop_table("user_contexts")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
