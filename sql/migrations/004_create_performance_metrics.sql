-- ============================================
-- Migración 004: Tabla performance_metrics
-- ============================================
-- Esta tabla almacena métricas de rendimiento del sistema por tenant
-- Created: 2026-03-18
-- ============================================

-- Tabla de métricas de rendimiento
CREATE TABLE IF NOT EXISTS performance_metrics (
    -- Identificación
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    hour INTEGER,  -- NULL = agregación diaria completa
    
    -- Métricas de latencia (en milisegundos)
    avg_response_time_ms DECIMAL(10, 2) DEFAULT 0,
    p50_response_time_ms DECIMAL(10, 2) DEFAULT 0,
    p90_response_time_ms DECIMAL(10, 2) DEFAULT 0,
    p95_response_time_ms DECIMAL(10, 2) DEFAULT 0,
    p99_response_time_ms DECIMAL(10, 2) DEFAULT 0,
    max_response_time_ms INTEGER DEFAULT 0,
    min_response_time_ms INTEGER DEFAULT 0,
    
    -- Métricas de throughput
    total_requests INTEGER NOT NULL DEFAULT 0,
    successful_requests INTEGER NOT NULL DEFAULT 0,
    failed_requests INTEGER NOT NULL DEFAULT 0,
    requests_per_minute DECIMAL(10, 2) DEFAULT 0,
    
    -- Métricas de errores
    error_rate DECIMAL(6, 4) DEFAULT 0,
    timeout_count INTEGER NOT NULL DEFAULT 0,
    validation_error_count INTEGER NOT NULL DEFAULT 0,
    auth_error_count INTEGER NOT NULL DEFAULT 0,
    rate_limit_hits INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de recursos
    avg_cpu_usage DECIMAL(5, 2) DEFAULT 0,
    avg_memory_usage_mb INTEGER DEFAULT 0,
    avg_database_connections INTEGER DEFAULT 0,
    peak_database_connections INTEGER DEFAULT 0,
    
    -- Métricas de cache
    cache_hit_rate DECIMAL(6, 4) DEFAULT 0,
    cache_miss_count INTEGER NOT NULL DEFAULT 0,
    cache_hit_count INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de API externa
    external_api_calls INTEGER NOT NULL DEFAULT 0,
    external_api_failures INTEGER NOT NULL DEFAULT 0,
    external_api_avg_latency_ms DECIMAL(10, 2) DEFAULT 0,
    
    -- Métricas de LLM
    llm_calls INTEGER NOT NULL DEFAULT 0,
    llm_total_tokens BIGINT NOT NULL DEFAULT 0,
    llm_prompt_tokens BIGINT NOT NULL DEFAULT 0,
    llm_completion_tokens BIGINT NOT NULL DEFAULT 0,
    llm_avg_latency_ms DECIMAL(10, 2) DEFAULT 0,
    llm_cost_usd DECIMAL(10, 4) DEFAULT 0,
    
    -- Campos de control
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date_hour UNIQUE (tenant_id, date, hour)
);

-- Indices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_performance_metrics_tenant_date 
    ON performance_metrics (tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_date 
    ON performance_metrics (date);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_tenant 
    ON performance_metrics (tenant_id);

CREATE INDEX IF NOT EXISTS idx_performance_metrics_date_hour 
    ON performance_metrics (date, hour);

-- Índice para búsquedas de rendimiento
CREATE INDEX IF NOT EXISTS idx_performance_metrics_response_time 
    ON performance_metrics (tenant_id, date DESC, avg_response_time_ms DESC);

-- Habilitar RLS
ALTER TABLE performance_metrics ENABLE ROW LEVEL SECURITY;

-- Política RLS para tenants
CREATE POLICY "Users can view own tenant performance metrics" 
    ON performance_metrics FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_performance_metrics_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para updated_at
CREATE TRIGGER trigger_update_performance_metrics
    BEFORE UPDATE ON performance_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_performance_metrics_updated_at();

-- Función para calcular error rate automáticamente
CREATE OR REPLACE FUNCTION calculate_performance_error_rate()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.total_requests > 0 THEN
        NEW.error_rate = NEW.failed_requests::DECIMAL / NEW.total_requests::DECIMAL;
    END IF;
    
    IF (NEW.cache_hit_count + NEW.cache_miss_count) > 0 THEN
        NEW.cache_hit_rate = NEW.cache_hit_count::DECIMAL / 
            (NEW.cache_hit_count + NEW.cache_miss_count)::DECIMAL;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para calcular error rate
CREATE TRIGGER trigger_calculate_performance_error_rate
    BEFORE INSERT OR UPDATE ON performance_metrics
    FOR EACH ROW
    EXECUTE FUNCTION calculate_performance_error_rate();

-- Vista útil para dashboards de rendimiento
CREATE OR REPLACE VIEW v_performance_summary AS
SELECT 
    tenant_id,
    date,
    AVG(avg_response_time_ms) as avg_response_time_ms,
    AVG(requests_per_minute) as avg_rpm,
    SUM(total_requests) as total_requests,
    AVG(error_rate) as avg_error_rate,
    AVG(cache_hit_rate) as avg_cache_hit_rate,
    SUM(llm_total_tokens) as total_tokens,
    SUM(llm_cost_usd) as total_llm_cost
FROM performance_metrics
GROUP BY tenant_id, date;

-- Comentarios
COMMENT ON TABLE performance_metrics IS 'Métricas de rendimiento del sistema por tenant';
COMMENT ON COLUMN performance_metrics.p50_response_time_ms IS 'Percentil 50 de tiempo de respuesta';
COMMENT ON COLUMN performance_metrics.p90_response_time_ms IS 'Percentil 90 de tiempo de respuesta';
COMMENT ON COLUMN performance_metrics.p95_response_time_ms IS 'Percentil 95 de tiempo de respuesta';
COMMENT ON COLUMN performance_metrics.p99_response_time_ms IS 'Percentil 99 de tiempo de respuesta';
COMMENT ON COLUMN performance_metrics.rate_limit_hits IS 'Número de veces que se alcanzó el rate limit';
COMMENT ON COLUMN performance_metrics.llm_cost_usd IS 'Costo estimado de LLM en dólares';
