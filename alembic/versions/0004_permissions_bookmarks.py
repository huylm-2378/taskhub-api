"""Add active users, admin roles and per-user task bookmarks.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False))
        batch.add_column(sa.Column("role", sa.String(5), server_default="USER", nullable=False))
        batch.create_check_constraint("user_role", "role IN ('USER', 'ADMIN')")
    op.create_table(
        "bookmarks",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bookmarks_task_id", "bookmarks", ["task_id"])


def downgrade() -> None:
    op.drop_table("bookmarks")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("user_role", type_="check")
        batch.drop_column("role")
        batch.drop_column("is_active")
