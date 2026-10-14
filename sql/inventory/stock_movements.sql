-- TABLA: stock_movements
CREATE TABLE IF NOT EXISTS stock_movements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tenant_id VARCHAR(100) NOT NULL,
    movement_type VARCHAR(50) NOT NULL,
    quantity INTEGER NOT NULL,
    stock_before INTEGER NOT NULL,
    stock_after INTEGER NOT NULL,
    reference_id UUID,
    reference_type VARCHAR(50),
    user_id UUID,
    reason TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_movement_type CHECK (movement_type IN ('sale', 'purchase', 'adjustment', 'return', 'damage', 'transfer', 'reservation', 'release')),
    CONSTRAINT valid_stock_calculation CHECK (stock_before + quantity = stock_after)
);

CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_movements_tenant ON stock_movements(tenant_id);
CREATE INDEX IF NOT EXISTS idx_movements_created ON stock_movements(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_movements_type ON stock_movements(movement_type);
CREATE INDEX IF NOT EXISTS idx_movements_reference ON stock_movements(reference_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_movements_product_date ON stock_movements(product_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_movements_tenant_date ON stock_movements(tenant_id, created_at DESC);

-- FUNCION: log_stock_movement
DROP FUNCTION IF EXISTS log_stock_movement(UUID, VARCHAR, VARCHAR, INTEGER, UUID, VARCHAR, UUID, TEXT, TEXT);
CREATE FUNCTION log_stock_movement(p_product_id UUID, p_tenant_id VARCHAR, p_movement_type VARCHAR, p_quantity INTEGER, p_reference_id UUID DEFAULT NULL, p_reference_type VARCHAR DEFAULT NULL, p_user_id UUID DEFAULT NULL, p_reason TEXT DEFAULT NULL, p_notes TEXT DEFAULT NULL)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_stock_before INTEGER;
    v_stock_after INTEGER;
    v_movement_id UUID;
BEGIN
    SELECT stock INTO v_stock_before FROM products WHERE id = p_product_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Product not found';
    END IF;
    v_stock_after := v_stock_before + p_quantity;
    INSERT INTO stock_movements (product_id, tenant_id, movement_type, quantity, stock_before, stock_after, reference_id, reference_type, user_id, reason, notes)
    VALUES (p_product_id, p_tenant_id, p_movement_type, p_quantity, v_stock_before, v_stock_after, p_reference_id, p_reference_type, p_user_id, p_reason, p_notes)
    RETURNING id INTO v_movement_id;
    RETURN v_movement_id;
END;
$$;

-- FUNCION: get_stock_history
DROP FUNCTION IF EXISTS get_stock_history(UUID, INTEGER);
CREATE FUNCTION get_stock_history(p_product_id UUID, p_limit INTEGER DEFAULT 50)
RETURNS TABLE(id UUID, movement_type VARCHAR, quantity INTEGER, stock_before INTEGER, stock_after INTEGER, reason TEXT, created_at TIMESTAMP)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY SELECT sm.id, sm.movement_type, sm.quantity, sm.stock_before, sm.stock_after, sm.reason, sm.created_at
    FROM stock_movements sm WHERE sm.product_id = p_product_id ORDER BY sm.created_at DESC LIMIT p_limit;
END;
$$;

-- TRIGGER: auto_log_stock_change
DROP TRIGGER IF EXISTS auto_log_stock_change ON products;
DROP FUNCTION IF EXISTS trigger_log_stock_change();
CREATE FUNCTION trigger_log_stock_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.stock != OLD.stock THEN
        PERFORM log_stock_movement(NEW.id, NEW.tenant_id::VARCHAR, 'adjustment', (NEW.stock - OLD.stock), NULL, NULL, NULL, 'Auto-detected stock change', NULL);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER auto_log_stock_change AFTER UPDATE OF stock ON products FOR EACH ROW EXECUTE FUNCTION trigger_log_stock_change();

-- RLS
ALTER TABLE stock_movements ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON stock_movements;
CREATE POLICY tenant_isolation ON stock_movements FOR ALL USING (tenant_id = current_setting('app.current_tenant', TRUE)::TEXT);
