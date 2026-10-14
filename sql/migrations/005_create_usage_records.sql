-- =====================================================
-- Migración 005: Tabla de Registros de Uso (Usage Records)
-- Fecha: 2026-03-20
-- Descripción: Almacena registros diarios de uso por tenant
-- =====================================================

-- Tabla principal de registros de uso
CREATE TABLE IF NOT EXISTS usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    record_date DATE NOT NULL DEFAULT CURRENT_DATE,
    
    -- Métricas de mensajes
    messages_count INTEGER DEFAULT 0,
    messages_limit INTEGER DEFAULT 0,
    
    -- Métricas de storage (MB)
    storage_used_mb DECIMAL(10, 2) DEFAULT 0,
    storage_limit_mb DECIMAL(10, 2) DEFAULT 0,
    storage_breakdown JSONB DEFAULT '{}',
    
    -- Métricas de API calls
    api_calls_count INTEGER DEFAULT 0,
    api_calls_limit INTEGER DEFAULT 0,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint único: un registro por tenant por día
    UNIQUE(tenant_id, record_date)
);

-- Índice para consultas rápidas por tenant y fecha
CREATE INDEX IF NOT EXISTS idx_usage_records_tenant_date 
    ON usage_records(tenant_id, record_date DESC);

-- Índice para búsquedas por fecha
CREATE INDEX IF NOT EXISTS idx_usage_records_date 
    ON usage_records(record_date DESC);

-- Tabla de logs de llamadas API (detallado)
CREATE TABLE IF NOT EXISTS api_call_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Proveedor y endpoint
    api_provider VARCHAR(50) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    
    -- Métricas
    tokens_used INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 6) DEFAULT 0,
    
    -- Timestamps
    called_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para api_call_logs
CREATE INDEX IF NOT EXISTS idx_api_call_logs_tenant 
    ON api_call_logs(tenant_id, called_at DESC);

CREATE INDEX IF NOT EXISTS idx_api_call_logs_provider 
    ON api_call_logs(api_provider, called_at DESC);

-- Comentarios
COMMENT ON TABLE usage_records IS 'Registros diarios de uso por tenant';
COMMENT ON TABLE api_call_logs IS 'Logs detallados de llamadas a APIs externas';
