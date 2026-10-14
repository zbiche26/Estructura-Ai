-- =====================================================
-- Migración 007: Suscripciones de Tenants
-- Fecha: 2026-03-20
-- Descripción: Define la suscripción activa de cada tenant
-- =====================================================

-- Tabla de suscripciones de tenants
CREATE TABLE IF NOT EXISTS tenant_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES subscription_plans(id),
    
    -- Estado de suscripción
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'trialing', 'past_due', 'canceled', 'paused'
    
    -- Período de facturación actual
    current_period_start DATE NOT NULL,
    current_period_end DATE NOT NULL,
    
    -- Período de trial
    trial_start DATE,
    trial_end DATE,
    
    -- Cancelación
    canceled_at TIMESTAMPTZ,
    cancellation_reason VARCHAR(255),
    
    -- Pausa
    pause_start DATE,
    pause_end DATE,
    
    -- Uso acumulado del ciclo actual
    messages_used_this_period INTEGER DEFAULT 0,
    storage_used_this_period DECIMAL(10, 2) DEFAULT 0,
    api_calls_used_this_period INTEGER DEFAULT 0,
    
    -- Configuración de billing
    billing_email VARCHAR(255),
    billing_cycle VARCHAR(20) DEFAULT 'monthly',  -- 'monthly', 'yearly'
    billing_address JSONB DEFAULT '{}',
    
    -- Fechas de facturación
    next_billing_date DATE,
    last_invoice_id UUID,
    
    -- Configuración de overages
    allow_overages BOOLEAN DEFAULT false,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_tenant 
    ON tenant_subscriptions(tenant_id);

CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_status 
    ON tenant_subscriptions(status);

CREATE INDEX IF NOT EXISTS idx_tenant_subscriptions_period 
    ON tenant_subscriptions(current_period_start, current_period_end);

-- Tabla de historial de cambios de plan
CREATE TABLE IF NOT EXISTS subscription_plan_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID NOT NULL REFERENCES tenant_subscriptions(id),
    
    -- Plan anterior y nuevo
    from_plan_id UUID REFERENCES subscription_plans(id),
    to_plan_id UUID REFERENCES subscription_plans(id),
    
    -- Tipo de cambio
    change_type VARCHAR(20) NOT NULL,  -- 'upgrade', 'downgrade', 'trial_start', 'trial_end', 'cancel'
    
    -- Fechas
    effective_from DATE NOT NULL,
    effective_to DATE,
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_subscription_plan_changes_tenant 
    ON subscription_plan_changes(tenant_id, created_at DESC);

-- Función para crear suscripción por defecto al crear tenant
CREATE OR REPLACE FUNCTION create_default_subscription()
RETURNS TRIGGER AS $$
BEGIN
    -- Obtener ID del plan free
    INSERT INTO tenant_subscriptions (
        tenant_id,
        plan_id,
        status,
        current_period_start,
        current_period_end,
        trial_start,
        trial_end
    )
    SELECT 
        NEW.id,
        (SELECT id FROM subscription_plans WHERE plan_key = 'free' LIMIT 1),
        'active',
        CURRENT_DATE,
        CURRENT_DATE + INTERVAL '1 month',
        CURRENT_DATE,
        CURRENT_DATE + INTERVAL '14 days'  -- 14 días de trial
    ON CONFLICT (tenant_id) DO NOTHING;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para crear suscripción al crear tenant
DROP TRIGGER IF EXISTS trigger_create_default_subscription ON tenants;
CREATE TRIGGER trigger_create_default_subscription
    AFTER INSERT ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION create_default_subscription();

-- Comentarios
COMMENT ON TABLE tenant_subscriptions IS 'Suscripción activa de cada tenant';
COMMENT ON TABLE subscription_plan_changes IS 'Historial de cambios de plan';
COMMENT ON COLUMN tenant_subscriptions.status IS 'Estado: active, trialing, past_due, canceled, paused';
