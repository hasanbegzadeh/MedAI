"""RadAI — Add model_versions and model_metrics tables, add model_version_id to ai_jobs."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_model_registry"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(128), nullable=True),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="testing"),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_model_versions_name_status",
        "model_versions",
        ["model_name", "status"],
    )

    op.create_table(
        "model_metrics",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("metric_value", sa.Float, nullable=False),
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studies.id"),
            nullable=True,
        ),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_model_metrics_version_id",
        "model_metrics",
        ["model_version_id"],
    )

    op.add_column(
        "ai_jobs",
        sa.Column(
            "model_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("model_versions.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ai_jobs_model_version_id",
        "ai_jobs",
        ["model_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_jobs_model_version_id", table_name="ai_jobs")
    op.drop_column("ai_jobs", "model_version_id")
    op.drop_index("ix_model_metrics_version_id", table_name="model_metrics")
    op.drop_table("model_metrics")
    op.drop_index("ix_model_versions_name_status", table_name="model_versions")
    op.drop_table("model_versions")
