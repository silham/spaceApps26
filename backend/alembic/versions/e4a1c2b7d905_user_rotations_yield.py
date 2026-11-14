"""User-built rotations and per-season yield results (D15).

Revision ID: e4a1c2b7d905
Revises: c7d92e1a460b
"""
from alembic import op
import sqlalchemy as sa

revision = "e4a1c2b7d905"
down_revision = "c7d92e1a460b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategy", sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("result", sa.Column("season_index", sa.Integer(), nullable=True))
    op.add_column("result", sa.Column("crop_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("result", "crop_id")
    op.drop_column("result", "season_index")
    op.drop_column("strategy", "superseded")
