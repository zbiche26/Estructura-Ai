-- Guard de idempotencia para respuestas duplicadas del agente (mensajes dobles)
-- Columna replied_at: NULL = todavía no se reclamó el envío de respuesta.
-- Se marca con un UPDATE condicional (WHERE replied_at IS NULL) justo antes
-- de llamar al agente, de forma que solo la primera ejecución para un
-- mismo whatsapp_message_id pueda proceder a generar y enviar la respuesta.
ALTER TABLE message_jobs
ADD COLUMN IF NOT EXISTS replied_at TIMESTAMPTZ;

-- Acelera el UPDATE ... WHERE whatsapp_message_id = ? AND replied_at IS NULL
-- (whatsapp_message_id ya es UNIQUE, este índice solo ayuda al filtro combinado)
CREATE INDEX IF NOT EXISTS idx_message_jobs_replied_at
ON message_jobs (whatsapp_message_id)
WHERE replied_at IS NULL;
