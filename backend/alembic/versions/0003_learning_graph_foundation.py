"""learning graph foundation

Revision ID: 0003_learning_graph
Revises: 0002_ctx_def_vocab
Create Date: 2026-02-28 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003_learning_graph"
down_revision: Union[str, None] = "0002_ctx_def_vocab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_interests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("interest_key", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "interest_key", name="uq_user_interest_key"),
    )
    op.create_index(op.f("ix_user_interests_id"), "user_interests", ["id"], unique=False)
    op.create_index(op.f("ix_user_interests_user_id"), "user_interests", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_interests_interest_key"), "user_interests", ["interest_key"], unique=False)

    op.create_table(
        "topic_clusters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("cluster_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "cluster_key", name="uq_topic_cluster_user_key"),
    )
    op.create_index(op.f("ix_topic_clusters_id"), "topic_clusters", ["id"], unique=False)
    op.create_index(op.f("ix_topic_clusters_user_id"), "topic_clusters", ["user_id"], unique=False)
    op.create_index(op.f("ix_topic_clusters_cluster_key"), "topic_clusters", ["cluster_key"], unique=False)

    op.create_table(
        "word_senses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("english_lemma", sa.String(length=200), nullable=False),
        sa.Column("semantic_key", sa.String(length=120), nullable=False),
        sa.Column("russian_translation", sa.String(length=200), nullable=False),
        sa.Column("context_definition_ru", sa.Text(), nullable=True),
        sa.Column("source_sentence", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("topic_cluster_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topic_cluster_id"], ["topic_clusters.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "english_lemma", "semantic_key", name="uq_word_sense_user_lemma_key"),
    )
    op.create_index(op.f("ix_word_senses_id"), "word_senses", ["id"], unique=False)
    op.create_index(op.f("ix_word_senses_user_id"), "word_senses", ["user_id"], unique=False)
    op.create_index(op.f("ix_word_senses_english_lemma"), "word_senses", ["english_lemma"], unique=False)
    op.create_index(op.f("ix_word_senses_semantic_key"), "word_senses", ["semantic_key"], unique=False)
    op.create_index(op.f("ix_word_senses_topic_cluster_id"), "word_senses", ["topic_cluster_id"], unique=False)

    op.create_table(
        "vocabulary_sense_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("vocabulary_item_id", sa.Integer(), nullable=False),
        sa.Column("word_sense_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vocabulary_item_id"], ["vocabulary_items.id"]),
        sa.ForeignKeyConstraint(["word_sense_id"], ["word_senses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "vocabulary_item_id", name="uq_vocab_sense_link_user_vocab"),
    )
    op.create_index(op.f("ix_vocabulary_sense_links_id"), "vocabulary_sense_links", ["id"], unique=False)
    op.create_index(op.f("ix_vocabulary_sense_links_user_id"), "vocabulary_sense_links", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_vocabulary_sense_links_vocabulary_item_id"),
        "vocabulary_sense_links",
        ["vocabulary_item_id"],
        unique=False,
    )
    op.create_index(op.f("ix_vocabulary_sense_links_word_sense_id"), "vocabulary_sense_links", ["word_sense_id"], unique=False)

    op.create_table(
        "mistake_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("english_lemma", sa.String(length=200), nullable=True),
        sa.Column("word_sense_id", sa.Integer(), nullable=True),
        sa.Column("mistake_tag", sa.String(length=120), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("expected_answer", sa.String(length=1000), nullable=True),
        sa.Column("user_answer", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["word_sense_id"], ["word_senses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mistake_events_id"), "mistake_events", ["id"], unique=False)
    op.create_index(op.f("ix_mistake_events_user_id"), "mistake_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_mistake_events_session_id"), "mistake_events", ["session_id"], unique=False)
    op.create_index(op.f("ix_mistake_events_english_lemma"), "mistake_events", ["english_lemma"], unique=False)
    op.create_index(op.f("ix_mistake_events_word_sense_id"), "mistake_events", ["word_sense_id"], unique=False)
    op.create_index(op.f("ix_mistake_events_mistake_tag"), "mistake_events", ["mistake_tag"], unique=False)
    op.create_index(op.f("ix_mistake_events_created_at"), "mistake_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mistake_events_created_at"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_mistake_tag"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_word_sense_id"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_english_lemma"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_session_id"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_user_id"), table_name="mistake_events")
    op.drop_index(op.f("ix_mistake_events_id"), table_name="mistake_events")
    op.drop_table("mistake_events")

    op.drop_index(op.f("ix_vocabulary_sense_links_word_sense_id"), table_name="vocabulary_sense_links")
    op.drop_index(op.f("ix_vocabulary_sense_links_vocabulary_item_id"), table_name="vocabulary_sense_links")
    op.drop_index(op.f("ix_vocabulary_sense_links_user_id"), table_name="vocabulary_sense_links")
    op.drop_index(op.f("ix_vocabulary_sense_links_id"), table_name="vocabulary_sense_links")
    op.drop_table("vocabulary_sense_links")

    op.drop_index(op.f("ix_word_senses_topic_cluster_id"), table_name="word_senses")
    op.drop_index(op.f("ix_word_senses_semantic_key"), table_name="word_senses")
    op.drop_index(op.f("ix_word_senses_english_lemma"), table_name="word_senses")
    op.drop_index(op.f("ix_word_senses_user_id"), table_name="word_senses")
    op.drop_index(op.f("ix_word_senses_id"), table_name="word_senses")
    op.drop_table("word_senses")

    op.drop_index(op.f("ix_topic_clusters_cluster_key"), table_name="topic_clusters")
    op.drop_index(op.f("ix_topic_clusters_user_id"), table_name="topic_clusters")
    op.drop_index(op.f("ix_topic_clusters_id"), table_name="topic_clusters")
    op.drop_table("topic_clusters")

    op.drop_index(op.f("ix_user_interests_interest_key"), table_name="user_interests")
    op.drop_index(op.f("ix_user_interests_user_id"), table_name="user_interests")
    op.drop_index(op.f("ix_user_interests_id"), table_name="user_interests")
    op.drop_table("user_interests")
