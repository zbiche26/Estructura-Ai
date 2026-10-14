-- ============================================
-- TABLA: stock_alerts
-- Alertas de stock bajo
-- ============================================

CREATE TABLE IF NOT EXISTS stock_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tenant_id VARCHAR(100) NOT NULL,

    current_stock INTEGER NOT NULL,
    threshold INTEGER NOT NULL,

    severity VARCHAR(20) NOT NULL DEFAULT 'warning',
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    resolved_at TIMESTAMP,
    resolved_by VARCHAR(100),
    resolution_notes TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_severity CHECK (severity IN ('warning','critical')),
    CONSTRAINT valid_status CHECK (status IN ('active','resolved','acknowledged'))
);

-- Índices

CREATE INDEX IF NOT EXISTS idx_alerts_product
ON stock_alerts(product_id);

CREATE INDEX IF NOT EXISTS idx_alerts_tenant
ON stock_alerts(tenant_id);

CREATE INDEX IF NOT EXISTS idx_alerts_status
ON stock_alerts(status)
WHERE status='active';

CREATE INDEX IF NOT EXISTS idx_alerts_severity
ON stock_alerts(severity)
WHERE status='active';

CREATE INDEX IF NOT EXISTS idx_alerts_created
ON stock_alerts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_active_tenant
ON stock_alerts(tenant_id,status,severity)
WHERE status='active';

-- ============================================
-- FUNCIONES
-- ============================================

DROP FUNCTION IF EXISTS create_stock_alert(UUID,VARCHAR,INTEGER,INTEGER);

CREATE FUNCTION create_stock_alert(
    p_product_id UUID,
    p_tenant_id VARCHAR,
    p_current_stock INTEGER,
    p_threshold INTEGER
)
RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_alert_id UUID;
    v_severity VARCHAR;
BEGIN

    IF p_current_stock <= 5 THEN
        v_severity := 'critical';
    ELSE
        v_severity := 'warning';
    END IF;

    IF EXISTS (
        SELECT 1 FROM stock_alerts
        WHERE product_id=p_product_id
        AND status='active'
    ) THEN

        SELECT id INTO v_alert_id
        FROM stock_alerts
        WHERE product_id=p_product_id
        AND status='active'
        LIMIT 1;

        RETURN v_alert_id;

    END IF;

    INSERT INTO stock_alerts(
        product_id,
        tenant_id,
        current_stock,
        threshold,
        severity,
        status
    )
    VALUES(
        p_product_id,
        p_tenant_id,
        p_current_stock,
        p_threshold,
        v_severity,
        'active'
    )
    RETURNING id INTO v_alert_id;

    RETURN v_alert_id;

END;
$$;


DROP FUNCTION IF EXISTS resolve_stock_alert(UUID,VARCHAR);

CREATE FUNCTION resolve_stock_alert(
    p_alert_id UUID,
    p_resolved_by VARCHAR DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
BEGIN

    UPDATE stock_alerts
    SET status='resolved',
        resolved_at=NOW(),
        resolved_by=p_resolved_by
    WHERE id=p_alert_id
    AND status='active';

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;

END;
$$;


DROP FUNCTION IF EXISTS get_active_alerts(VARCHAR,INTEGER);

CREATE FUNCTION get_active_alerts(
    p_tenant_id VARCHAR DEFAULT NULL,
    p_limit INTEGER DEFAULT 50
)
RETURNS TABLE(
    id UUID,
    product_id UUID,
    current_stock INTEGER,
    threshold INTEGER,
    severity VARCHAR,
    status VARCHAR,
    created_at TIMESTAMP
)
LANGUAGE plpgsql
AS $$
BEGIN

RETURN QUERY
SELECT
    sa.id,
    sa.product_id,
    sa.current_stock,
    sa.threshold,
    sa.severity,
    sa.status,
    sa.created_at
FROM stock_alerts sa
WHERE sa.status='active'
AND (p_tenant_id IS NULL OR sa.tenant_id=p_tenant_id)
ORDER BY
    CASE sa.severity
        WHEN 'critical' THEN 1
        WHEN 'warning' THEN 2
    END,
    sa.created_at DESC
LIMIT p_limit;

END;
$$;

-- ============================================
-- RLS
-- ============================================

ALTER TABLE stock_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON stock_alerts;

CREATE POLICY tenant_isolation
ON stock_alerts
FOR ALL
USING (tenant_id = current_setting('app.current_tenant', TRUE)::TEXT);

-- ============================================
-- FUNCIONES RPC INVENTORY
-- ============================================

DROP FUNCTION IF EXISTS update_product_stock(UUID,INTEGER);

CREATE FUNCTION update_product_stock(
    p_product_id UUID,
    p_quantity_change INTEGER
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_stock INTEGER;
    v_new_stock INTEGER;
BEGIN

SELECT stock INTO v_current_stock
FROM products
WHERE id=p_product_id;

IF NOT FOUND THEN
    RAISE EXCEPTION 'Product not found';
END IF;

v_new_stock := v_current_stock + p_quantity_change;

IF v_new_stock < 0 THEN
    RAISE EXCEPTION 'Stock cannot be negative';
END IF;

UPDATE products
SET stock=v_new_stock,
updated_at=NOW()
WHERE id=p_product_id;

RETURN TRUE;

END;
$$;


DROP FUNCTION IF EXISTS get_stock_history(UUID,INTEGER);

CREATE FUNCTION get_stock_history(
    p_product_id UUID,
    p_limit INTEGER DEFAULT 50
)
RETURNS TABLE(
    id UUID,
    movement_type VARCHAR,
    quantity INTEGER,
    stock_before INTEGER,
    stock_after INTEGER,
    reason TEXT,
    created_at TIMESTAMP
)
LANGUAGE plpgsql
AS $$
BEGIN

RETURN QUERY
SELECT
    sm.id,
    sm.movement_type,
    sm.quantity,
    sm.stock_before,
    sm.stock_after,
    sm.reason,
    sm.created_at
FROM stock_movements sm
WHERE sm.product_id=p_product_id
ORDER BY sm.created_at DESC
LIMIT p_limit;

END;
$$;

-- ============================================
-- ÍNDICES GENERALES
-- ============================================

CREATE INDEX IF NOT EXISTS idx_products_name_search
ON products USING gin(to_tsvector('spanish',name));

CREATE INDEX IF NOT EXISTS idx_products_category
ON products(category);

CREATE INDEX IF NOT EXISTS idx_products_available
ON products(is_active,stock)
WHERE is_active=true AND stock>0;

CREATE INDEX IF NOT EXISTS idx_products_price
ON products(price);

CREATE INDEX IF NOT EXISTS idx_products_tenant
ON products(tenant_id);

CREATE INDEX IF NOT EXISTS idx_products_composite
ON products(tenant_id,is_active,category);

CREATE INDEX IF NOT EXISTS idx_products_tenant_name
ON products(tenant_id,name);


CREATE INDEX IF NOT EXISTS idx_conversations_tenant_date
ON conversations(tenant_id,created_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
ON messages(conversation_id,created_at);

CREATE INDEX IF NOT EXISTS idx_sales_date
ON sales(created_at DESC);
