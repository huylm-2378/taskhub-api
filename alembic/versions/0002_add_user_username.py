"""Add unique usernames, preserving existing users.

Revision ID: 0002
Revises: 770764801816
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "770764801816"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(64), nullable=True))
    users = sa.table("users", sa.column("id", sa.Uuid()), sa.column("username", sa.String(64)))
    # UUIDs are already unique. Both SQLite and PostgreSQL support this expression.
    op.execute(users.update().values(
        username=sa.literal("user_") + sa.func.replace(sa.cast(users.c.id, sa.String), "-", "")
    ))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("username", existing_type=sa.String(64), nullable=False)
        batch.create_index("ix_users_username", ["username"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_username")
        batch.drop_column("username")
