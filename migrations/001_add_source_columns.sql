-- Migração 001: suporte a múltiplas fontes de vagas (crawler multi-site).
-- Executar como dbadmin:
--   psql -U dbadmin -d application_db -f migrations/001_add_source_columns.sql
\set ON_ERROR_STOP on

SET search_path TO application, public;

ALTER TABLE vagas
    ADD COLUMN IF NOT EXISTS fonte VARCHAR(50) NOT NULL DEFAULT 'linkedin',
    ADD COLUMN IF NOT EXISTS source_job_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS apply_mode VARCHAR(20) NOT NULL DEFAULT 'assisted',
    ADD COLUMN IF NOT EXISTS hash_dedupe CHAR(64),
    ALTER COLUMN linkedin_job_id DROP NOT NULL;

UPDATE vagas
SET source_job_id = linkedin_job_id
WHERE source_job_id IS NULL AND linkedin_job_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_vagas_fonte_source
    ON vagas (fonte, source_job_id);

CREATE INDEX IF NOT EXISTS idx_vagas_hash_dedupe ON vagas (hash_dedupe);
CREATE INDEX IF NOT EXISTS idx_vagas_fonte ON vagas (fonte);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA application TO svc_application;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA application TO svc_application;
