"""learning graph relations

Revision ID: 0004_learning_graph_relations
Revises: 0003_learning_graph
Create Date: 2026-03-09 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004_learning_graph_relations"
down_revision: Union[str, None] = "0003_learning_graph"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sense_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("left_sense_id", sa.Integer(), nullable=False),
        sa.Column("right_sense_id", sa.Integer(), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["left_sense_id"], ["word_senses.id"]),
        sa.ForeignKeyConstraint(["right_sense_id"], ["word_senses.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "left_sense_id", "right_sense_id", name="uq_sense_relation_pair"),
    )
    op.create_index(op.f("ix_sense_relations_id"), "sense_relations", ["id"], unique=False)
    op.create_index(op.f("ix_sense_relations_user_id"), "sense_relations", ["user_id"], unique=False)
    op.create_index(op.f("ix_sense_relations_left_sense_id"), "sense_relations", ["left_sense_id"], unique=False)
    op.create_index(op.f("ix_sense_relations_right_sense_id"), "sense_relations", ["right_sense_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_sense_relations_right_sense_id"), table_name="sense_relations")
    op.drop_index(op.f("ix_sense_relations_left_sense_id"), table_name="sense_relations")
    op.drop_index(op.f("ix_sense_relations_user_id"), table_name="sense_relations")
    op.drop_index(op.f("ix_sense_relations_id"), table_name="sense_relations")
    op.drop_table("sense_relations")
