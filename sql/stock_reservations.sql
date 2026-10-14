-- ============================================
-- TABLA: stock_reservations
-- Gestión de reservas de stock durante conversaciones
-- ============================================

CREATE TABLE IF NOT EXISTS stock_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Relaciones
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    tenant_id VARCHAR(100) NOT NULL,
    
    -- Datos de la reserva
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    -- status: 'active', 'released', 'completed'
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    released_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Metadatos
    notes TEXT,
    
    -- Índices inline
    CONSTRAINT valid_quantity CHECK (quantity > 0),
    CONSTRAINT valid_status CHECK (status IN ('active', 'released', 'completed'))
);

-- Índices para performance
CREATE INDEX idx_reservations_product ON stock_reservations(product_id);
CREATE INDEX idx_reservations_conversation ON stock_reservations(conversation_id);
CREATE INDEX idx_reservations_tenant ON stock_reservations(tenant_id);
CREATE INDEX idx_reservations_status ON stock_reservations(status) WHERE status = 'active';
CREATE INDEX idx_reservations_expires ON stock_reservations(expires_at) WHERE status = 'active';

-- Índice compuesto para queries frecuentes
CREATE INDEX idx_reservations_active 
ON stock_reservations(product_id, status, expires_at) 
WHERE status = 'active';

-- ============================================
-- FUNCIÓN: Obtener stock disponible
-- ============================================

CREATE OR REPLACE FUNCTION get_available_stock(p_product_id UUID)
RETURNS TABLE (
    total_stock INTEGER,
    reserved_stock INTEGER,
    available_stock INTEGER
) AS $$
DECLARE
    v_total INTEGER;
    v_reserved INTEGER;
BEGIN
    -- Obtener stock total del producto
    SELECT stock INTO v_total
    FROM products
    WHERE id = p_product_id;
    
    -- Calcular stock reservado activo (no expirado)
    SELECT COALESCE(SUM(quantity), 0) INTO v_reserved
    FROM stock_reservations
    WHERE product_id = p_product_id
      AND status = 'active'
      AND expires_at > NOW();
    
    -- Retornar resultados
    RETURN QUERY
    SELECT 
        v_total as total_stock,
        v_reserved as reserved_stock,
        (v_total - v_reserved) as available_stock;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- FUNCIÓN: Limpiar reservas expiradas
-- ============================================

CREATE OR REPLACE FUNCTION cleanup_expired_reservations()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER;
BEGIN
    UPDATE stock_reservations
    SET status = 'released',
        released_at = NOW()
    WHERE status = 'active'
      AND expires_at <= NOW();
    
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- TRIGGER: Auto-limpiar reservas expiradas
-- ============================================

-- Job programado (ejecutar cada 5 minutos)
-- En Supabase: Database → Cron Jobs
-- Función: cleanup_expired_reservations()
-- Schedule: */5 * * * * (cada 5 minutos)

-- ============================================
-- POLÍTICAS RLS (Row Level Security)
-- ============================================

ALTER TABLE stock_reservations ENABLE ROW LEVEL SECURITY;

-- Policy: Los usuarios solo ven reservas de su tenant
CREATE POLICY tenant_isolation ON stock_reservations
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant', TRUE)::TEXT);

-- ============================================
-- DATOS DE PRUEBA (opcional)
-- ============================================

-- Ejemplo de reserva
-- INSERT INTO stock_reservations (
--     product_id,
--     conversation_id,
--     tenant_id,
--     quantity,
--     expires_at
-- ) VALUES (
--     'product-uuid',
--     'conversation-uuid',
--     'demo',
--     2,
--     NOW() + INTERVAL '30 minutes'
-- );