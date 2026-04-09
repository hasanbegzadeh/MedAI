-- RadAI PostgreSQL Schema
-- Run automatically by Docker on first start

-- ─── Extensions ──────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─── Users & RBAC ────────────────────────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    VARCHAR(64) UNIQUE NOT NULL,
    email       VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role        VARCHAR(32) NOT NULL CHECK (role IN ('radiologist', 'resident', 'admin')) DEFAULT 'resident',
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Studies ─────────────────────────────────────────────────────────────────
CREATE TABLE studies (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    orthanc_id          VARCHAR(64) UNIQUE NOT NULL,    -- Orthanc internal StudyID
    study_instance_uid  VARCHAR(128) UNIQUE NOT NULL,   -- DICOM StudyInstanceUID
    accession_number    VARCHAR(64),
    modality            VARCHAR(16) NOT NULL,            -- CT, MR, CR, US, MG ...
    body_part           VARCHAR(64),                     -- CHEST, ABDOMEN, BRAIN ...
    study_description   VARCHAR(255),
    anonymized_uid      VARCHAR(128),                    -- UUID used for cloud uploads
    num_series          INTEGER DEFAULT 0,
    num_instances       INTEGER DEFAULT 0,
    ai_status           VARCHAR(32) NOT NULL DEFAULT 'pending'
                            CHECK (ai_status IN ('pending','queued','processing','completed','failed','skipped')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_studies_modality ON studies(modality);
CREATE INDEX idx_studies_ai_status ON studies(ai_status);

-- ─── AI Jobs ─────────────────────────────────────────────────────────────────
CREATE TABLE ai_jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    study_id        UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    job_type        VARCHAR(64) NOT NULL,   -- totalsegmentator, nninteractive, nodule_detection ...
    celery_task_id  VARCHAR(128),
    status          VARCHAR(32) NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','completed','failed','cancelled')),
    tier            SMALLINT NOT NULL DEFAULT 1 CHECK (tier IN (1, 2, 3)),
    model_name      VARCHAR(128),
    progress_pct    SMALLINT DEFAULT 0,
    error_message   TEXT,
    result_json     JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_ai_jobs_study ON ai_jobs(study_id);
CREATE INDEX idx_ai_jobs_status ON ai_jobs(status);

-- ─── Findings ────────────────────────────────────────────────────────────────
CREATE TABLE findings (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    study_id                UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    ai_job_id               UUID REFERENCES ai_jobs(id),
    finding_type            VARCHAR(64) NOT NULL,           -- nodule, lesion, organ_volume ...
    location                VARCHAR(128),                   -- "Right Upper Lobe"
    laterality              VARCHAR(16),                    -- left, right, bilateral
    segmentation_id         VARCHAR(128),                   -- DICOM-SEG reference
    series_instance_uid     VARCHAR(128),
    sop_instance_uid        VARCHAR(128),
    slice_index             INTEGER,
    measurements            JSONB,                          -- {longest_diameter_mm, volume_mm3, mean_hu}
    characteristics         TEXT[],                         -- ["solid", "spiculated"]
    confidence              NUMERIC(4,3),                   -- 0.000–1.000
    lung_rads_category      VARCHAR(16),
    li_rads_category        VARCHAR(16),
    status                  VARCHAR(32) NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','accepted','rejected','modified')),
    radiologist_notes       TEXT,
    reviewed_by             UUID REFERENCES users(id),
    reviewed_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_findings_study ON findings(study_id);
CREATE INDEX idx_findings_status ON findings(status);

-- ─── Reports ─────────────────────────────────────────────────────────────────
CREATE TABLE reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    study_id            UUID NOT NULL REFERENCES studies(id) ON DELETE CASCADE,
    report_type         VARCHAR(32) NOT NULL DEFAULT 'draft',
    template_name       VARCHAR(64),                        -- lung_rads, li_rads, general_ct
    content_text        TEXT,                               -- Final report text
    content_html        TEXT,                               -- HTML-formatted report
    dicom_sr_uid        VARCHAR(128),                       -- DICOM-SR SOP Instance UID
    classification      VARCHAR(32),                        -- Lung-RADS 3, LI-RADS 4 ...
    ai_polished         BOOLEAN DEFAULT false,
    ai_model_used       VARCHAR(128),                       -- e.g. MedAIBase/MedGemma1.5:4b-it
    signed_by           UUID REFERENCES users(id),
    signed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reports_study ON reports(study_id);

-- ─── Audit Log ────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    study_id    UUID REFERENCES studies(id),
    action      VARCHAR(64) NOT NULL,       -- study.loaded, ai.run, finding.accepted, report.signed
    entity_type VARCHAR(32),
    entity_id   UUID,
    detail      JSONB,
    ip_address  INET,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_study ON audit_log(study_id);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_time ON audit_log(created_at DESC);

-- ─── Seed: default admin user (change password immediately) ─────────────────
-- Password: 'changeme' hashed with bcrypt cost 12
INSERT INTO users (username, email, password_hash, role)
VALUES ('admin', 'admin@radai.local',
        '$2b$12$BbJhK7T6P0g.n5F0AjJn8uiMfQfCmjKP6JQE3OaJkSb8EX9GHWJ2.',
        'admin')
ON CONFLICT DO NOTHING;
