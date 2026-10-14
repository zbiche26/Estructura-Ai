-- ============================================
-- Migración 002: Tabla intent_metrics
-- ============================================
-- Esta tabla almacena métricas diarias de intenciones por tenant
-- Created: 2026-03-18
-- ============================================

-- Tabla de métricas de intenciones
CREATE TABLE IF NOT EXISTS intent_metrics (
    -- Identificación
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    
    -- Información de la intención
    intent_name VARCHAR(100) NOT NULL,
    intent_category VARCHAR(50),
    
    -- Métricas de volumen
    total_intents INTEGER NOT NULL DEFAULT 0,
    successful_intents INTEGER NOT NULL DEFAULT 0,
    failed_intents INTEGER NOT NULL DEFAULT 0,
    escalation_intents INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de confianza
    avg_confidence_score DECIMAL(5, 4) DEFAULT 0,
    min_confidence_score DECIMAL(5, 4) DEFAULT 0,
    max_confidence_score DECIMAL(5, 4) DEFAULT 0,
    
    -- Métricas de tiempo
    avg_processing_time_ms INTEGER NOT NULL DEFAULT 0,
    total_processing_time_ms BIGINT NOT NULL DEFAULT 0,
    
    -- Métricas de tokens
    total_tokens_used BIGINT NOT NULL DEFAULT 0,
    avg_tokens_per_intent DECIMAL(10, 2) DEFAULT 0,
    
    -- Métricas de conversación
    intents_in_new_conversations INTEGER NOT NULL DEFAULT 0,
    intents_in_existing_conversations INTEGER NOT NULL DEFAULT 0,
    
    -- Campos de control
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date_intent UNIQUE (tenant_id, date, intent_name)
);

-- Indices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_intent_metrics_tenant_date 
    ON intent_metrics (tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_intent_metrics_date 
    ON intent_metrics (date);

CREATE INDEX IF NOT EXISTS idx_intent_metrics_tenant_intent 
    ON intent_metrics (tenant_id, intent_name);

CREATE INDEX IF NOT EXISTS idx_intent_metrics_intent_category 
    ON intent_metrics (intent_category);

-- Habilitar RLS
ALTER TABLE intent_metrics ENABLE ROW LEVEL SECURITY;

-- Política RLS para tenants
CREATE POLICY "Users can view own tenant intent metrics" 
    ON intent_metrics FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_intent_metrics_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para updated_at
CREATE TRIGGER trigger_update_intent_metrics
    BEFORE UPDATE ON intent_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_intent_metrics_updated_at();

-- Comentarios
COMMENT ON TABLE intent_metrics IS 'Métricas diarias de intenciones por tenant';
COMMENT ON COLUMN intent_metrics.intent_name IS 'Nombre de la intención (e.g., purchase, inquiry, greeting)';
COMMENT ON COLUMN intent_metrics.intent_category IS 'Categoría de la intención (e.g., sales, support, general)';
COMMENT ON COLUMN intent_metrics.avg_confidence_score IS 'Puntuación de confianza promedio (0-1)';
COMMENT ON COLUMN intent_metrics.escalation_intents IS 'Intenciones que requirieron escalamiento a humano';
