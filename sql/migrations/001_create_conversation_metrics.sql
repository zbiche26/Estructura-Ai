-- ============================================
-- Migración 001: Tabla conversation_metrics
-- ============================================
-- Esta tabla almacena métricas diarias de conversaciones por tenant
-- Created: 2026-03-18
-- ============================================

-- Tabla de métricas de conversaciones
CREATE TABLE IF NOT EXISTS conversation_metrics (
    -- Identificación
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    
    -- Métricas de volumen
    total_conversations INTEGER NOT NULL DEFAULT 0,
    active_conversations INTEGER NOT NULL DEFAULT 0,
    closed_conversations INTEGER NOT NULL DEFAULT 0,
    archived_conversations INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de mensajes
    total_messages INTEGER NOT NULL DEFAULT 0,
    total_user_messages INTEGER NOT NULL DEFAULT 0,
    total_assistant_messages INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de tokens
    total_tokens_used BIGINT NOT NULL DEFAULT 0,
    avg_tokens_per_conversation DECIMAL(10, 2) DEFAULT 0,
    
    -- Métricas de tiempo
    avg_response_time_seconds DECIMAL(10, 2) DEFAULT 0,
    avg_conversation_duration_minutes DECIMAL(10, 2) DEFAULT 0,
    
    -- Métricas por plataforma
    whatsapp_conversations INTEGER NOT NULL DEFAULT 0,
    web_conversations INTEGER NOT NULL DEFAULT 0,
    telegram_conversations INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de engagement
    new_users INTEGER NOT NULL DEFAULT 0,
    returning_users INTEGER NOT NULL DEFAULT 0,
    
    -- Campos de control
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date UNIQUE (tenant_id, date)
);

-- Indices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_conversation_metrics_tenant_date 
    ON conversation_metrics (tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_conversation_metrics_date 
    ON conversation_metrics (date);

CREATE INDEX IF NOT EXISTS idx_conversation_metrics_tenant 
    ON conversation_metrics (tenant_id);

-- Habilitar RLS
ALTER TABLE conversation_metrics ENABLE ROW LEVEL SECURITY;

-- Política RLS para tenants
CREATE POLICY "Users can view own tenant metrics" 
    ON conversation_metrics FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_conversation_metrics_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para updated_at
CREATE TRIGGER trigger_update_conversation_metrics
    BEFORE UPDATE ON conversation_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_metrics_updated_at();

-- Comentarios
COMMENT ON TABLE conversation_metrics IS 'Métricas diarias de conversaciones por tenant';
COMMENT ON COLUMN conversation_metrics.total_conversations IS 'Total de conversaciones en el día';
COMMENT ON COLUMN conversation_metrics.active_conversations IS 'Conversaciones activas (no cerradas)';
COMMENT ON COLUMN conversation_metrics.avg_response_time_seconds IS 'Tiempo promedio de respuesta en segundos';
