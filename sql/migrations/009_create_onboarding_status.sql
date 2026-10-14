-- ============================================
-- Migración 009: Tabla onboarding_status
-- ============================================
-- Guarda el progreso del wizard de onboarding por tenant.
-- El GET /onboarding/status debe leer de esta tabla en lugar
-- de retornar valores hardcodeados.
-- Created: 2026-04-29
-- ============================================

CREATE TABLE IF NOT EXISTS onboarding_status (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id               UUID NOT NULL,

    -- Pasos del wizard
    whatsapp_connected      BOOLEAN NOT NULL DEFAULT FALSE,
    training_done           BOOLEAN NOT NULL DEFAULT FALSE,
    first_conversation_done BOOLEAN NOT NULL DEFAULT FALSE,

    -- Se setea automáticamente cuando todos los pasos son true
    completed_at            TIMESTAMPTZ DEFAULT NULL,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Un solo registro por tenant
    CONSTRAINT unique_onboarding_tenant UNIQUE (tenant_id)
);

-- Índice para lookup por tenant
CREATE INDEX IF NOT EXISTS idx_onboarding_status_tenant
    ON onboarding_status (tenant_id);

-- RLS
ALTER TABLE onboarding_status ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant can view own onboarding status"
    ON onboarding_status FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY "Tenant can upsert own onboarding status"
    ON onboarding_status FOR INSERT
    WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY "Tenant can update own onboarding status"
    ON onboarding_status FOR UPDATE
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Función: actualiza updated_at y setea completed_at automáticamente
CREATE OR REPLACE FUNCTION update_onboarding_status_timestamps()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();

    -- Marca completed_at solo cuando todos los pasos son true
    IF NEW.whatsapp_connected = TRUE
       AND NEW.training_done = TRUE
       AND NEW.first_conversation_done = TRUE
       AND NEW.completed_at IS NULL
    THEN
        NEW.completed_at = NOW();
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_onboarding_status_timestamps
    BEFORE UPDATE ON onboarding_status
    FOR EACH ROW
    EXECUTE FUNCTION update_onboarding_status_timestamps();

COMMENT ON TABLE onboarding_status IS 'Estado del wizard de onboarding por tenant';
COMMENT ON COLUMN onboarding_status.completed_at IS 'Seteado automáticamente cuando los tres pasos son true';
