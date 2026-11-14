"""Seasonal-forecast snapshots per farm (D16).

Revision ID: a3f6d1e8c204
Revises: e4a1c2b7d905
"""
from alembic import op
import sqlalchemy as sa

revision = "a3f6d1e8c204"
down_revision = "e4a1c2b7d905"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_snapshot",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("site_id", sa.String(64), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_start", sa.Date(), nullable=False),
        sa.Column("forecast_end", sa.Date(), nullable=False),
        sa.Column("n_members", sa.Integer(), nullable=False),
        sa.Column("monthly_raw_path", sa.Text(), nullable=False),
        sa.Column("monthly_raw_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_forecast_snapshot_site_id", "forecast_snapshot", ["site_id"])


def downgrade() -> None:
    op.drop_index("ix_forecast_snapshot_site_id", table_name="forecast_snapshot")
    op.drop_table("forecast_snapshot")
