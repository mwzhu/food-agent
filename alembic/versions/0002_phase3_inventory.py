"""Phase 3 inventory support."""

from alembic import op
import sqlalchemy as sa


revision = "0002_phase3_inventory"
down_revision = "0001_phase1_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fridge_items",
        sa.Column("item_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("user_profiles.user_id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("category", sa.String(length=24), nullable=False, server_default="pantry"),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fridge_items_user_id", "fridge_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_fridge_items_user_id", table_name="fridge_items")
    op.drop_table("fridge_items")
