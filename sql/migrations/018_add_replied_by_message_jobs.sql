-- Columna replied_by: identifica qué proceso (hostname:pid) ganó el
-- reclamo de un job de message_jobs -- tanto el claim atómico de
-- 'processing' del worker (message_worker.py::_process_job) como el
-- claim de replied_at del agent_reply_handler (_claim_reply) escriben
-- aquí. Bajo el invariante de que el claim de 'processing' ahora es
-- atómico (WHERE status='pending'), ambos claims para un mismo mensaje
-- siempre los gana el mismo proceso; si algún día aparece evidencia de
-- lo contrario, es la prueba directa de que dos procesos compitieron
-- por la misma cola -- ver
-- spec/07-investigacion-mensajes-duplicados-2026-07-07.md.
ALTER TABLE message_jobs
ADD COLUMN IF NOT EXISTS replied_by TEXT;
