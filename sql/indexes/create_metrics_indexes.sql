-- ============================================
-- Índices adicionales de Performance para métricas
-- ============================================
-- Created: 2026-03-18
-- ============================================

-- ============================================
-- ÍNDICES PARA conversation_metrics
-- ============================================

-- Índice para consultas de tendencias (últimos 30 días)
CREATE INDEX IF NOT EXISTS idx_conversation_metrics_trends 
    ON conversation_metrics (tenant_id, date DESC);

-- Índice para métricas por plataforma
CREATE INDEX IF NOT EXISTS idx_conversation_metrics_platform 
    ON conversation_metrics (tenant_id, date, whatsapp_conversations, web_conversations);

-- Índice para búsquedas de usuarios nuevos vs recurrentes
CREATE INDEX IF NOT EXISTS idx_conversation_metrics_users 
    ON conversation_metrics (tenant_id, date, new_users, returning_users);

-- ============================================
-- ÍNDICES PARA intent_metrics
-- ============================================

-- Índice para análisis de tendencias de intenciones
CREATE INDEX IF NOT EXISTS idx_intent_metrics_trends 
    ON intent_metrics (tenant_id, date DESC, intent_name);

-- Índice para métricas por categoría
CREATE INDEX IF NOT EXISTS idx_intent_metrics_category_trends 
    ON intent_metrics (tenant_id, date DESC, intent_category);

-- Índice para análisis de confianza
CREATE INDEX IF NOT EXISTS idx_intent_metrics_confidence 
    ON intent_metrics (tenant_id, date DESC, avg_confidence_score);

-- Índice para detecciones de escalamiento
CREATE INDEX IF NOT EXISTS idx_intent_metrics_escalation 
    ON intent_metrics (tenant_id, date DESC, escalation_intents DESC);

-- ============================================
-- ÍNDICES PARA product_metrics
-- ============================================

-- Índice para productos más buscados
CREATE INDEX IF NOT EXISTS idx_product_metrics_searches 
    ON product_metrics (tenant_id, date DESC, search_queries DESC);

-- Índice para productos más comprados
CREATE INDEX IF NOT EXISTS idx_product_metrics_purchases 
    ON product_metrics (tenant_id, date DESC, times_purchased DESC);

-- Índice para CTR de búsqueda
CREATE INDEX IF NOT EXISTS idx_product_metrics_search_ctr 
    ON product_metrics (tenant_id, date DESC, search_ctr DESC);

-- Índice para CTR de recomendaciones
CREATE INDEX IF NOT EXISTS idx_product_metrics_recommendation_ctr 
    ON product_metrics (tenant_id, date DESC, recommendation_ctr DESC);

-- Índice para análisis por categoría
CREATE INDEX IF NOT EXISTS idx_product_metrics_category_performance 
    ON product_metrics (tenant_id, category, date DESC);

-- ============================================
-- ÍNDICES PARA performance_metrics
-- ============================================

-- Índice para análisis de latencia
CREATE INDEX IF NOT EXISTS idx_performance_metrics_latency 
    ON performance_metrics (tenant_id, date DESC, avg_response_time_ms DESC);

-- Índice para análisis de errores
CREATE INDEX IF NOT EXISTS idx_performance_metrics_errors 
    ON performance_metrics (tenant_id, date DESC, error_rate DESC);

-- Índice para análisis de uso de cache
CREATE INDEX IF NOT EXISTS idx_performance_metrics_cache 
    ON performance_metrics (tenant_id, date DESC, cache_hit_rate DESC);

-- Índice para análisis de costos LLM
CREATE INDEX IF NOT EXISTS idx_performance_metrics_llm_cost 
    ON performance_metrics (tenant_id, date DESC, llm_cost_usd DESC);

-- Índice para análisis de rate limiting
CREATE INDEX IF NOT EXISTS idx_performance_metrics_rate_limit 
    ON performance_metrics (tenant_id, date DESC, rate_limit_hits DESC);

-- Índice para análisis por hora
CREATE INDEX IF NOT EXISTS idx_performance_metrics_hourly 
    ON performance_metrics (tenant_id, date, hour);

-- ============================================
-- ÍNDICES COMPUESTOS PARA DASHBOARDS
-- ============================================

-- Dashboard de overview diario
CREATE INDEX IF NOT EXISTS idx_metrics_daily_overview 
    ON conversation_metrics (tenant_id, date DESC);

-- Dashboard de análisis de productos
CREATE INDEX IF NOT EXISTS idx_metrics_product_analysis 
    ON product_metrics (tenant_id, date DESC, category, search_queries DESC);

-- Dashboard de rendimiento del sistema
CREATE INDEX IF NOT EXISTS idx_metrics_system_performance 
    ON performance_metrics (tenant_id, date DESC, total_requests, error_rate);

-- ============================================
-- NOTES SOBRE OPTIMIZACIÓN
-- ============================================
-- Estos índices están diseñados para soportar los siguientes casos de uso:
-- 1. Consultas de tendencias (últimos 7, 30, 90 días)
-- 2. Dashboards en tiempo real
-- 3. Reportes semanales y mensuales
-- 4. Análisis de rendimiento
-- 5. Detección de anomalías
--
-- Se recomienda analizar el uso de estos índices periódicamente
-- y eliminar los que no se utilicen con frecuencia.
