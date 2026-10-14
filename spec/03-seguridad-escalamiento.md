← [Índice](./README.md) · ← [02-arquitectura-backend.md](./02-arquitectura-backend.md)

# Fase 3 — Seguridad y escalamiento (rumbo a 5–15 clientes)

- Probar explícitamente el aislamiento de RLS en Supabase: confirmar con un test que el tenant A no puede leer datos del tenant B bajo ninguna condición.
- Confirmar que existen backups automáticos activos y probar al menos una vez el proceso de restauración.
- Monitoreo de salud más allá del endpoint `/health`: alertas si el worker de mensajes se detiene, si sube la tasa de error, o si Qdrant deja de responder.
- Definir política de retención de datos personales de clientes finales (relevante bajo regulación local en Colombia / LATAM).

---
→ Siguiente: [04-seguridad-formal.md](./04-seguridad-formal.md)
