-- ============================================
-- Migración 010: Tabla notifications
-- ============================================
-- Notificaciones del sistema por tenant:
-- alertas de facturación, onboarding, límites de plan
-- y rendimiento del agente.
-- Created: 2026-04-29
-- ============================================

-- Tipo de notificación
CREATE TYPE notification_type AS ENUM (
    'billing',
    'onboarding',
    'limit',
    'performance'
);

CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,

    type        notification_type NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,

    -- NULL = no leída, timestamp = leída
    read_at     TIMESTAMPTZ DEFAULT NULL,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_notifications_tenant
    ON notifications (tenant_id);

CREATE INDEX IF NOT EXISTS idx_notifications_tenant_unread
    ON notifications (tenant_id, read_at)
    WHERE read_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_notifications_created_at
    ON notifications (created_at DESC);

-- RLS
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant can view own notifications"
    ON notifications FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

CREATE POLICY "Tenant can update own notifications"
    ON notifications FOR UPDATE
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- Seed: notificación de prueba para que el frontend pueda testear la UI
-- (reemplazar '<TENANT_ID_DE_PRUEBA>' con un UUID real antes de ejecutar)
/*
INSERT INTO notifications (tenant_id, type, title, body) VALUES
    ('<TENANT_ID_DE_PRUEBA>', 'onboarding',  'Bienvenido a Estructura AI',         'Completa los pasos de configuración para comenzar.'),
    ('<TENANT_ID_DE_PRUEBA>', 'billing',     'Tu suscripción está activa',          'Plan Starter activado correctamente.'),
    ('<TENANT_ID_DE_PRUEBA>', 'limit',       'Límite de conversaciones al 80%',     'Llevas 800 de 1000 conversaciones del mes.'),
    ('<TENANT_ID_DE_PRUEBA>', 'performance', 'Tiempo de respuesta elevado',         'Tu agente tardó más de 10s en las últimas 5 conversaciones.');
*/

COMMENT ON TABLE notifications IS 'Notificaciones del sistema por tenant';
COMMENT ON COLUMN notifications.read_at IS 'NULL = no leída. Se setea con PATCH /notifications/{id}/read';
COMMENT ON COLUMN notifications.type IS 'billing | onboarding | limit | performance';
