"""RadAI — Initial migration: create all tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="resident"),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "studies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("orthanc_id", sa.String(64), unique=True, nullable=False),
        sa.Column("study_instance_uid", sa.String(128), unique=True, nullable=False),
        sa.Column("accession_number", sa.String(64)),
        sa.Column("modality", sa.String(16), nullable=False),
        sa.Column("body_part", sa.String(64)),
        sa.Column("study_description", sa.String(255)),
        sa.Column("anonymized_uid", sa.String(128)),
        sa.Column("num_series", sa.Integer, server_default=sa.text("0")),
        sa.Column("num_instances", sa.Integer, server_default=sa.text("0")),
        sa.Column("ai_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "ai_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("celery_task_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("tier", sa.SmallInteger, nullable=False, server_default=sa.text("1")),
        sa.Column("model_name", sa.String(128)),
        sa.Column("progress_pct", sa.SmallInteger, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text),
        sa.Column("result_json", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_table(
        "findings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ai_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_jobs.id")
        ),
        sa.Column("finding_type", sa.String(64), nullable=False),
        sa.Column("location", sa.String(128)),
        sa.Column("laterality", sa.String(16)),
        sa.Column("segmentation_id", sa.String(128)),
        sa.Column("series_instance_uid", sa.String(128)),
        sa.Column("sop_instance_uid", sa.String(128)),
        sa.Column("slice_index", sa.Integer),
        sa.Column("measurements", postgresql.JSONB),
        sa.Column("characteristics", postgresql.ARRAY(sa.Text)),
        sa.Column("confidence", sa.Float),
        sa.Column("lung_rads_category", sa.String(16)),
        sa.Column("li_rads_category", sa.String(16)),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("radiologist_notes", sa.Text),
        sa.Column(
            "reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "study_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_type", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("template_name", sa.String(64)),
        sa.Column("content_text", sa.Text),
        sa.Column("content_html", sa.Text),
        sa.Column("dicom_sr_uid", sa.String(128)),
        sa.Column("classification", sa.String(32)),
        sa.Column("ai_polished", sa.Boolean, server_default=sa.text("false")),
        sa.Column("ai_model_used", sa.String(128)),
        sa.Column(
            "signed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")
        ),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column(
            "study_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("studies.id")
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("detail", postgresql.JSONB),
        sa.Column("ip_address", postgresql.INET),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )

    op.create_index("ix_ai_jobs_study_id", "ai_jobs", ["study_id"])
    op.create_index("ix_findings_study_id", "findings", ["study_id"])
    op.create_index("ix_findings_ai_job_id", "findings", ["ai_job_id"])
    op.create_index("ix_reports_study_id", "reports", ["study_id"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_study_id", "audit_log", ["study_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("reports")
    op.drop_table("findings")
    op.drop_table("ai_jobs")
    op.drop_table("studies")
    op.drop_table("users")
