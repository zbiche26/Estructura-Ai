-- ============================================
-- Migración 003: Tabla product_metrics
-- ============================================
-- Esta tabla almacena métricas diarias de productos por tenant
-- Created: 2026-03-18
-- ============================================

-- Tabla de métricas de productos
CREATE TABLE IF NOT EXISTS product_metrics (
    -- Identificación
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    date DATE NOT NULL,
    
    -- Información del producto
    product_id UUID NOT NULL,
    product_sku VARCHAR(50),
    product_name VARCHAR(255),
    category VARCHAR(100),
    
    -- Métricas de búsqueda
    search_queries INTEGER NOT NULL DEFAULT 0,
    search_impressions INTEGER NOT NULL DEFAULT 0,
    search_clicks INTEGER NOT NULL DEFAULT 0,
    search_ctr DECIMAL(6, 4) DEFAULT 0,  -- Click-through rate
    
    -- Métricas de recomendación
    recommendations_shown INTEGER NOT NULL DEFAULT 0,
    recommendations_clicked INTEGER NOT NULL DEFAULT 0,
    recommendation_ctr DECIMAL(6, 4) DEFAULT 0,
    
    -- Métricas de conversación
    times_mentioned INTEGER NOT NULL DEFAULT 0,
    times_in_cart INTEGER NOT NULL DEFAULT 0,
    times_purchased INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de intención de compra
    inquiry_count INTEGER NOT NULL DEFAULT 0,
    price_query_count INTEGER NOT NULL DEFAULT 0,
    availability_query_count INTEGER NOT NULL DEFAULT 0,
    
    -- Métricas de engagement
    avg_time_on_product_seconds INTEGER NOT NULL DEFAULT 0,
    total_time_on_product_seconds BIGINT NOT NULL DEFAULT 0,
    
    -- Campos de control
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT unique_tenant_date_product UNIQUE (tenant_id, date, product_id)
);

-- Indices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_product_metrics_tenant_date 
    ON product_metrics (tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_product_metrics_date 
    ON product_metrics (date);

CREATE INDEX IF NOT EXISTS idx_product_metrics_tenant_product 
    ON product_metrics (tenant_id, product_id);

CREATE INDEX IF NOT EXISTS idx_product_metrics_category 
    ON product_metrics (category);

CREATE INDEX IF NOT EXISTS idx_product_metrics_product_date 
    ON product_metrics (product_id, date);

-- Habilitar RLS
ALTER TABLE product_metrics ENABLE ROW LEVEL SECURITY;

-- Política RLS para tenants
CREATE POLICY "Users can view own tenant product metrics" 
    ON product_metrics FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Función para actualizar timestamp
CREATE OR REPLACE FUNCTION update_product_metrics_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para updated_at
CREATE TRIGGER trigger_update_product_metrics
    BEFORE UPDATE ON product_metrics
    FOR EACH ROW
    EXECUTE FUNCTION update_product_metrics_updated_at();

-- Función para calcular CTR automáticamente
CREATE OR REPLACE FUNCTION calculate_product_ctr()
RETURNS TRIGGER AS $$
BEGIN
    -- Calcular search CTR
    IF NEW.search_impressions > 0 THEN
        NEW.search_ctr = NEW.search_clicks::DECIMAL / NEW.search_impressions::DECIMAL;
    END IF;
    
    -- Calcular recommendation CTR
    IF NEW.recommendations_shown > 0 THEN
        NEW.recommendation_ctr = NEW.recommendations_clicked::DECIMAL / NEW.recommendations_shown::DECIMAL;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para calcular CTR
CREATE TRIGGER trigger_calculate_product_ctr
    BEFORE INSERT OR UPDATE ON product_metrics
    FOR EACH ROW
    EXECUTE FUNCTION calculate_product_ctr();

-- Comentarios
COMMENT ON TABLE product_metrics IS 'Métricas diarias de productos por tenant';
COMMENT ON COLUMN product_metrics.search_ctr IS 'Tasa de clics en búsquedas (clicks/impressions)';
COMMENT ON COLUMN product_metrics.recommendation_ctr IS 'Tasa de clics en recomendaciones';
COMMENT ON COLUMN product_metrics.times_mentioned IS 'Veces que el producto fue mencionado en conversaciones';
COMMENT ON COLUMN product_metrics.times_in_cart IS 'Veces que el producto fue agregado al carrito';
COMMENT ON COLUMN product_metrics.times_purchased IS 'Veces que el producto fue comprado';
