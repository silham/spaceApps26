"""Accounts, expiring sessions and farm/run ownership. Existing unowned farms become invisible (D14).

Revision ID: c7d92e1a460b
Revises: a57b0ecd315d
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d92e1a460b"
down_revision = "a57b0ecd315d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "user_session",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_session_user_id", "user_session", ["user_id"])
    op.create_index("ix_user_session_expires_at", "user_session", ["expires_at"])
    for table in ("site", "simulation_run"):
        op.add_column(table, sa.Column("owner_user_id", sa.String(64), nullable=True))
        op.create_foreign_key(f"fk_{table}_owner_user", table, "app_user", ["owner_user_id"], ["id"])
        op.create_index(f"ix_{table}_owner_user_id", table, ["owner_user_id"])
    op.add_column("site", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("site", "archived")
    for table in ("simulation_run", "site"):
        op.drop_index(f"ix_{table}_owner_user_id", table)
        op.drop_constraint(f"fk_{table}_owner_user", table, type_="foreignkey")
        op.drop_column(table, "owner_user_id")
    op.drop_table("user_session")
    op.drop_table("app_user")
