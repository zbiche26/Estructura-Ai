-- Habilitación de identidad de réplica completa para sincronización en tiempo real (Tarea S02)
-- Esto permite que los eventos UPDATE incluyan los datos anteriores de la fila en el WAL.
ALTER TABLE messages REPLICA IDENTITY FULL;
