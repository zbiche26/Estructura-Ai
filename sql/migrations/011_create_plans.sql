-- ============================================
-- Migración 011: Tabla plans + seed inicial
-- ============================================
-- Los planes hoy están hardcodeados en src/core/plans.py.
-- Esta tabla permite actualizarlos sin tocar código.
-- El fallback en plans.py se mantiene hasta validar en producción.
-- Created: 2026-04-29
-- ============================================

CREATE TABLE IF NOT EXISTS plans (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    slug             TEXT NOT NULL UNIQUE,   -- starter | growth | enterprise

    -- Precios en COP (pesos colombianos)
    price_monthly    INTEGER NOT NULL DEFAULT 0,
    price_annual     INTEGER NOT NULL DEFAULT 0,
    activation_fee   INTEGER NOT NULL DEFAULT 0,

    -- Límites del plan (estructura flexible)
    limits           JSONB NOT NULL DEFAULT '{}',

    -- Features visibles al usuario
    features         JSONB NOT NULL DEFAULT '[]',

    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    is_public        BOOLEAN NOT NULL DEFAULT TRUE,

    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plans_slug
    ON plans (slug);

CREATE INDEX IF NOT EXISTS idx_plans_active_public
    ON plans (is_active, is_public);

-- RLS: planes públicos son visibles para todos
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public plans are readable by all"
    ON plans FOR SELECT
    USING (is_public = TRUE AND is_active = TRUE);

-- ============================================
-- Seed: los tres planes actuales del sistema
-- Valores tomados de src/core/plans.py y del
-- documento de requerimientos del frontend
-- ============================================
INSERT INTO plans (name, slug, price_monthly, price_annual, activation_fee, limits, features, is_active, is_public)
VALUES
(
    'Starter',
    'starter',
    290000,
    0,
    0,
    '{"max_agents": 1, "max_conversations_month": 1000, "max_team_members": 2, "max_products": 100}',
    '["1 agente IA", "1.000 conversaciones/mes", "2 usuarios", "Soporte por email"]',
    TRUE,
    TRUE
),
(
    'Growth',
    'growth',
    650000,
    0,
    0,
    '{"max_agents": 3, "max_conversations_month": 5000, "max_team_members": 5, "max_products": 500}',
    '["3 agentes IA", "5.000 conversaciones/mes", "5 usuarios", "Soporte prioritario", "Analytics avanzado"]',
    TRUE,
    TRUE
),
(
    'Enterprise',
    'enterprise',
    1200000,
    0,
    0,
    '{"max_agents": 10, "max_conversations_month": 20000, "max_team_members": 20, "max_products": 5000}',
    '["10 agentes IA", "20.000 conversaciones/mes", "20 usuarios", "Soporte dedicado", "Analytics avanzado", "Integraciones personalizadas"]',
    TRUE,
    TRUE
)
ON CONFLICT (slug) DO NOTHING;

-- ============================================
-- Downgrade (ejecutar solo para revertir)
-- ============================================
-- DROP TABLE IF EXISTS plans;

COMMENT ON TABLE plans IS 'Catálogo de planes de suscripción. Reemplaza los valores hardcodeados en src/core/plans.py';
COMMENT ON COLUMN plans.slug IS 'Identificador corto: starter | growth | enterprise. Debe coincidir con TenantPlanEnum';
COMMENT ON COLUMN plans.limits IS 'JSONB con max_agents, max_conversations_month, max_team_members, max_products';
COMMENT ON COLUMN plans.features IS 'Array JSONB de strings visibles al usuario en la UI de planes';
