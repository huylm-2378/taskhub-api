"""Durable jobs and idempotency keys.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("output", sa.LargeBinary()),
        sa.UniqueConstraint("owner_id", "kind", "idempotency_key", name="uq_jobs_owner_kind_key"),
        sa.CheckConstraint("kind IN ('export', 'reminder')", name="job_kind"),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'succeeded', 'failed', 'uncertain', 'skipped')",
            name="job_status",
        ),
    )
    op.create_index("ix_jobs_dispatch", "jobs", ["status", "available_at"])


def downgrade() -> None:
    op.drop_table("jobs")
