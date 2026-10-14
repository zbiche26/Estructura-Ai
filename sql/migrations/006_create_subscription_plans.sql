-- =====================================================
-- Migración 006: Catálogo de Planes de Suscripción
-- Fecha: 2026-03-20
-- Descripción: Define los planes disponibles y sus límites
-- =====================================================

-- Tabla de planes de suscripción
CREATE TABLE IF NOT EXISTS subscription_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_key VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    display_order INTEGER DEFAULT 0,
    
    -- Límites de mensajes
    messages_limit INTEGER DEFAULT 0,
    messages_limit_period VARCHAR(20) DEFAULT 'monthly',
    messages_overage_rate DECIMAL(10, 4) DEFAULT 0.0100,  -- $0.01 por mensaje extra
    
    -- Límites de storage (MB)
    storage_limit_mb DECIMAL(10, 2) DEFAULT 0,
    storage_overage_rate DECIMAL(10, 4) DEFAULT 0.1000,  -- $0.10 por MB extra
    
    -- Límites de API calls
    api_calls_limit INTEGER DEFAULT 0,
    api_calls_overage_rate DECIMAL(10, 6) DEFAULT 0.0010,  -- $0.001 por llamada extra
    
    -- Límites de productos
    products_limit INTEGER DEFAULT 0,
    
    -- Límites de conversaciones
    conversations_limit INTEGER DEFAULT 0,
    
    -- Límites de usuarios
    users_limit INTEGER DEFAULT 1,
    
    -- Límites de vectores (Qdrant)
    vectors_limit INTEGER DEFAULT 0,
    
    -- Precios
    monthly_price DECIMAL(10, 2) DEFAULT 0,
    yearly_price DECIMAL(10, 2) DEFAULT 0,
    
    -- Features (JSON array)
    features JSONB DEFAULT '[]',
    
    -- Metadatos
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insertar planes por defecto
INSERT INTO subscription_plans (
    plan_key, name, description, display_order,
    messages_limit, storage_limit_mb, api_calls_limit, 
    products_limit, conversations_limit, users_limit, vectors_limit,
    monthly_price, yearly_price, features
) VALUES 
(
    'free', 'Free', 'Plan gratuito para pruebas y pequeños negocios', 1,
    100, 100.00, 500,
    10, 50, 1, 1000,
    0.00, 0.00,
    '["basic_analytics", "whatsapp_basic", "email_support"]'::jsonb
),
(
    'pro', 'Pro', 'Plan profesional con más funcionalidades', 2,
    5000, 1000.00, 10000,
    500, 1000, 5, 10000,
    29.99, 299.99,
    '["basic_analytics", "advanced_analytics", "whatsapp_full", "api_access", "priority_support", "custom_reports"]'::jsonb
),
(
    'enterprise', 'Enterprise', 'Plan empresarial sin límites', 3,
    -1, -1.00, -1,  -- -1 indica ilimitado
    -1, -1, -1, -1,
    99.99, 999.99,
    '["basic_analytics", "advanced_analytics", "whatsapp_full", "api_access", "priority_support", "custom_reports", "dedicated_agent", "custom_integrations", "sla_guarantee"]'::jsonb
) ON CONFLICT (plan_key) DO NOTHING;

-- Índices
CREATE INDEX IF NOT EXISTS idx_subscription_plans_key 
    ON subscription_plans(plan_key);
    
CREATE INDEX IF NOT EXISTS idx_subscription_plans_active 
    ON subscription_plans(is_active) WHERE is_active = true;

-- Comentarios
COMMENT ON TABLE subscription_plans IS 'Catálogo de planes de suscripción disponibles';
COMMENT ON COLUMN subscription_plans.plan_key IS 'Identificador único del plan (free, pro, enterprise)';
COMMENT ON COLUMN subscription_plans.messages_limit IS 'Límite de mensajes (-1 = ilimitado)';
