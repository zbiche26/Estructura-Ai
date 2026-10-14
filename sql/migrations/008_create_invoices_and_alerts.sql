-- =====================================================
-- Migración 008: Facturas y Alertas de Uso
-- Fecha: 2026-03-20
-- =====================================================

-- Tabla de facturas
CREATE TABLE IF NOT EXISTS invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID NOT NULL REFERENCES tenant_subscriptions(id),
    
    -- Período facturado
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    
    -- Montos
    subtotal DECIMAL(10, 2) NOT NULL,
    tax_amount DECIMAL(10, 2) DEFAULT 0,
    discount_amount DECIMAL(10, 2) DEFAULT 0,
    total_amount DECIMAL(10, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    
    -- Estado
    status VARCHAR(20) DEFAULT 'draft',  -- 'draft', 'pending', 'paid', 'failed', 'cancelled', 'refunded'
    
    -- Detalle de uso
    usage_details JSONB DEFAULT '{}',
    line_items JSONB DEFAULT '[]',
    
    -- Información de pago
    payment_method VARCHAR(50),
    payment_reference VARCHAR(255),
    paid_at TIMESTAMPTZ,
    payment_failure_reason TEXT,
    
    -- Archivo
    pdf_url VARCHAR(500),
    
    -- Fechas
    due_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabla de alertas de uso
CREATE TABLE IF NOT EXISTS usage_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Tipo de alerta
    alert_type VARCHAR(50) NOT NULL,  -- 'messages', 'storage', 'api_calls', 'products'
    threshold_percent INTEGER NOT NULL,  -- 80, 100, 120, etc.
    
    -- Uso en el momento de la alerta
    usage_at_alert JSONB DEFAULT '{}',
    
    -- Estado
    is_read BOOLEAN DEFAULT false,
    is_sent BOOLEAN DEFAULT false,
    acknowledged_at TIMESTAMPTZ,
    
    -- Notificación
    notification_sent_at TIMESTAMPTZ,
    notification_method VARCHAR(20),  -- 'email', 'sms', 'webhook'
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para facturas
CREATE INDEX IF NOT EXISTS idx_invoices_tenant 
    ON invoices(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_status 
    ON invoices(status);

CREATE INDEX IF NOT EXISTS idx_invoices_number 
    ON invoices(invoice_number);

CREATE INDEX IF NOT EXISTS idx_invoices_period 
    ON invoices(period_start, period_end);

-- Índices para alertas de uso
CREATE INDEX IF NOT EXISTS idx_usage_alerts_tenant_unread 
    ON usage_alerts(tenant_id, is_read, created_at DESC)
    WHERE is_read = false;

CREATE INDEX IF NOT EXISTS idx_usage_alerts_type 
    ON usage_alerts(alert_type, created_at DESC);

-- Función para generar número de factura
CREATE OR REPLACE FUNCTION generate_invoice_number(tenant_id UUID, period_date DATE)
RETURNS TEXT AS $$
DECLARE
    year_part TEXT;
    tenant_code TEXT;
    sequence_num INTEGER;
    invoice_num TEXT;
BEGIN
    -- Obtener año del período
    year_part := TO_CHAR(period_date, 'YYYY');
    
    -- Obtener código corto del tenant (primeros 4 caracteres del ID)
    tenant_code := UPPER(LEFT(tenant_id::TEXT, 4));
    
    -- Obtener siguiente número de secuencia para este tenant/año
    SELECT COALESCE(MAX(
        CAST(SUBSTRING(invoice_number FROM 8 FOR 4) AS INTEGER)
    ), 0) + 1
    INTO sequence_num
    FROM invoices
    WHERE tenant_id = tenant_id 
    AND invoice_number LIKE 'INV-' || year_part || '-%';
    
    -- Formatear número
    invoice_num := 'INV-' || year_part || '-' || LPAD(sequence_num::TEXT, 4, '0');
    
    RETURN invoice_num;
END;
$$ LANGUAGE plpgsql;

-- Comentarios
COMMENT ON TABLE invoices IS 'Facturas generadas por tenant';
COMMENT ON TABLE usage_alerts IS 'Historial de alertas de uso enviadas';
COMMENT ON COLUMN invoices.status IS 'Estados: draft, pending, paid, failed, cancelled, refunded';
