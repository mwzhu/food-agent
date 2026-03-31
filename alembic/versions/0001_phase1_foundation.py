"""Phase 1 foundation schema."""

from alembic import op
import sqlalchemy as sa


revision = "0001_phase1_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=64), primary_key=True),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("weight_lbs", sa.Float(), nullable=False),
        sa.Column("height_in", sa.Float(), nullable=False),
        sa.Column("sex", sa.String(length=16), nullable=False),
        sa.Column("activity_level", sa.String(length=32), nullable=False),
        sa.Column("goal", sa.String(length=16), nullable=False),
        sa.Column("dietary_restrictions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("allergies", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("budget_weekly", sa.Float(), nullable=False, server_default="150"),
        sa.Column("household_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cooking_skill", sa.String(length=32), nullable=False, server_default="intermediate"),
        sa.Column("schedule_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "plan_runs",
        sa.Column("run_id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("user_profiles.user_id"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("state_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_plan_runs_user_id", "plan_runs", ["user_id"])
    op.create_index("ix_plan_runs_status", "plan_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_plan_runs_status", table_name="plan_runs")
    op.drop_index("ix_plan_runs_user_id", table_name="plan_runs")
    op.drop_table("plan_runs")
    op.drop_table("user_profiles")
