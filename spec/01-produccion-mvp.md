← [Índice](./README.md) · ← [00-entorno-dev.md](./00-entorno-dev.md)

# Fase 1 — Celeste a producción (mínimo viable decente)

Este es el bloque urgente. El orden importa: cada paso depende del anterior.

## 1. Merge y deploy

- [ ] Actualizar `main` local: `git checkout main && git pull origin main` (al 2026-07-06 el local estaba 18 commits detrás de `origin/main`, confirmar de nuevo antes de tocar nada)
- [ ] Sobre `fix/celeste-prompt-and-c07`: rebasar/mergear con `main` actualizado si hace falta
- [ ] Correr tests relevantes antes de seguir: `pytest tests/test_orchestrator.py tests/test_agent_edge_cases.py tests/test_intent_classifier_enhanced.py` como mínimo
- [ ] Sumar el fix del manejo 503 en `GET /agent/config` dentro del mismo PR (ver [00-entorno-dev.md § 0.3](./00-entorno-dev.md)) — única pieza de valor rescatable de `development`
- [ ] Merge de `fix/celeste-prompt-and-c07` a `main` (revisar diff con `--stat` primero, luego completo)
- [ ] Push a `main` → Railway despliega automáticamente
- [ ] Confirmar en logs de Railway que el deploy fue exitoso y la app arrancó sin errores

## 2. Poblar Qdrant con propiedades reales

- [ ] Conseguir el Excel actualizado de Eje Inmobiliario (posible bloqueo externo — pedir hoy si no se tiene)
- [ ] Verificar que el Excel tenga los campos correctos: nombre, barrio, precio, habitaciones, baños, parqueadero, mascotas, link de Facebook
- [ ] Correr el importer hacia la colección `products_{tenant_id}` de Eje Inmobiliario
- [ ] Verificar en Qdrant que los vectores quedaron cargados

## 3. Limpieza de detalles menores que interfieren con el prompt nuevo

- [ ] Eliminar el emoji 💡 hardcodeado en `response_generator.py` (método `_adjust_tone_by_stage`, líneas ~361-362, confirmado por auditoría 2026-07-06)
- [ ] Mover el número de escalamiento (3116457633) al campo `owner_phone` en `agent_config` de Supabase — **corrección de auditoría 2026-07-06:** está hardcodeado 4 veces dentro del texto del system prompt en `rag_system.py`, no solo en `response_generator.py` como se pensaba antes. Hay que sacarlo de las 4 ocurrencias en el prompt, no solo cambiar un valor de configuración.

## 4. Prueba end-to-end en WhatsApp real

Con deploy hecho y Qdrant poblado, probar el flujo completo con casos representativos:

- Saludo genérico
- Referencia directa a una propiedad del catálogo
- Afirmación corta ("sí", "ok")
- Solicitud de fotos
- Caso de interés real → verificar que escale correctamente al asesor humano

## 5. Cola de mensajes y calidad de respuesta — investigación 2026-07-07 (ver detalle en [07-investigacion-mensajes-duplicados-2026-07-07.md](./07-investigacion-mensajes-duplicados-2026-07-07.md))

**⚠️ CORRECCIÓN (2026-07-07, sesión posterior): el hallazgo "P0 — Pérdida silenciosa de mensajes en la cola" que estaba documentado aquí era incorrecto — queda descartado.** Se investigó a fondo cruzando logs de Railway con consultas directas a Supabase (`message_jobs` y `messages`) y se confirmó que los 4 wamid marcados como "nunca procesados" (`3EB0A41530...`, `AC15F4D3...`, `ACF478B7...` y `3EB0EE0035...` — este último con un fragmento mal transcrito originalmente como `3EB0EE0003`) en realidad se procesaron correctamente de punta a punta: `status=done`, sin error, con respuesta real enviada al cliente y confirmada en la tabla `messages`. La conclusión original probablemente vino de un log de Railway truncado/incompleto sin aviso, o de buscar en Supabase con los fragmentos de wamid mal transcritos. Detalle completo de la verificación en la sección 2 del documento de investigación linkeado arriba.

De la misma sesión de pruebas real de WhatsApp (2026-07-07, 14:50-14:55 hora Bogotá), salieron **3 problemas reales distintos**, con estado actual:

### 5.1 Mensajes duplicados — investigado, mitigación lista en rama sin mergear

El bot mandó 2 respuestas distintas para un mismo mensaje del cliente, en 2 ocasiones (327ms y 236ms de diferencia entre cada par). Investigación exhaustiva por código **no encontró la causa raíz exacta** (se descartaron: múltiples réplicas del servidor, doble suscripción al event bus, duplicación del payload de Meta, doble job en `message_jobs`, un mecanismo de timeout/watchdog — no existe ninguno en el código —, y respuestas manuales del dashboard). Se implementó un guard de idempotencia a nivel de base de datos (columna `message_jobs.replied_at`, reclamo atómico antes de llamar al agente) en la rama `fix/duplicate-reply-guard`, con TDD completo (RED→GREEN confirmado sobre código real) y logging `[GUARD]` explícito para capturar evidencia la próxima vez que ocurra. **Pendiente: correr la migración `017_add_replied_at_message_jobs.sql` contra producción (orden crítico: antes de desplegar el código, no después) y mergear la rama.** Ver sección 3 del documento de investigación.

### 5.2 Pérdida de contexto sobre qué propiedad se discute — sin investigar

El cliente preguntó por "casa de alcázares" (propiedad ya mostrada 2 veces antes en la misma conversación) y el bot respondió "No encontré propiedades exactas". Hipótesis sin confirmar: el RAG busca cada mensaje de forma aislada, sin enriquecer la query con el nombre de producto ya mencionado en el contexto de la conversación. Ver sección 4 del documento de investigación para el punto exacto del código a revisar (`agent_orchestrator.py::process_message`, pasos 5 y 7).

### 5.3 Silencio de ~1 minuto antes de responder — sin investigar

Ante el mensaje "aparta estudio" (typo), el bot tardó ~1 minuto en responder. No se determinó si la demora fue en el encolado, en que el worker lo recogiera, o dentro del pipeline del agente. Ver sección 5 del documento de investigación.

## 6. Duplicados de webhook (después de que el flujo base funcione)

- [ ] Investigar por qué la deduplicación existente no está atrapando todos los reenvíos de Meta

> Este punto se deja para después a propósito: no bloquea que Celeste empiece a responder, y es más fácil de diagnosticar con tráfico real ya corriendo.

---
→ Siguiente: [02-arquitectura-backend.md](./02-arquitectura-backend.md)
