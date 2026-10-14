-- ============================================
-- RLS: Políticas multi-tenant para tabla messages
-- ============================================
-- Garantiza que cada tenant solo vea y escriba
-- sus propios mensajes. Requerido para habilitar
-- Realtime en el frontend (useMessages.ts:51-53).
-- Created: 2026-04-29
-- ============================================

-- Habilitar RLS en la tabla messages
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- SELECT: un tenant solo lee sus propios mensajes
CREATE POLICY "Tenant can view own messages"
    ON messages FOR SELECT
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- INSERT: un tenant solo puede insertar en su propio canal
CREATE POLICY "Tenant can insert own messages"
    ON messages FOR INSERT
    WITH CHECK (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- UPDATE: un tenant solo puede modificar sus propios mensajes
CREATE POLICY "Tenant can update own messages"
    ON messages FOR UPDATE
    USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);

-- ============================================
-- INSTRUCCIONES DE VALIDACIÓN (ejecutar manualmente)
-- ============================================
-- Prueba de aislamiento entre dos tenants:
--
-- 1. Autenticarse como tenant_A y ejecutar:
--    SELECT * FROM messages;
--    → Solo debe devolver mensajes donde tenant_id = tenant_A
--
-- 2. Autenticarse como tenant_B y ejecutar:
--    SELECT * FROM messages;
--    → Solo debe devolver mensajes donde tenant_id = tenant_B
--
-- 3. Con tenant_A, intentar insertar un mensaje con tenant_id = tenant_B:
--    INSERT INTO messages (tenant_id, ...) VALUES ('<id_tenant_B>', ...);
--    → Debe fallar con error de política RLS
--
-- Una vez validado, notificar al equipo de frontend para que
-- descomenten el bloque de Realtime en useMessages.ts:51-53
-- ============================================
