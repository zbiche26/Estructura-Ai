← [Índice](./README.md) · ← [01-produccion-mvp.md](./01-produccion-mvp.md)

# Fase 2 — Backend: manejo de errores y arquitectura básica

Una vez Celeste esté respondiendo en producción, este es el siguiente bloque de trabajo. No es urgente para el lanzamiento, pero sí antes de sumar más clientes pagos.

## Manejo de errores

- Envolver en try/except toda llamada a servicios externos (Supabase, Qdrant, WhatsApp API, OpenAI) que pueda fallar por causas fuera de nuestro control.
- Nunca dejar que un error externo se propague como 500 crudo — responder con código HTTP controlado (404, 403, 503) y mensaje claro.
- Idempotencia: cualquier evento externo (webhook) debe poder recibirse más de una vez sin duplicar efectos — ya existe el patrón con el UNIQUE en `whatsapp_message_id`, extender el criterio a otros webhooks si aparecen.
- Cualquier ID proveniente de un sistema externo debe resolverse a un ID interno antes de usarse — no asumir que un ID externo es válido como ID propio (lección del fix de amnesia, ver [00-entorno-dev.md, sección 0.3](./00-entorno-dev.md)).

## Arquitectura y disciplina de capas

- Mantener la separación router → servicio → repository ya documentada en `docs/ARCHITECTURE.md`, incluso bajo presión de tiempo — la tentación más común es meter una query de Supabase directo en el router para "ir más rápido".
- Revisar y consolidar los archivos duplicados detectados (`conversation_repo.py` vs `conversation_repository.py`) — usar solo uno.

## Configuración y secretos

- Confirmar que ningún secreto (API keys, tokens de WhatsApp, service role key de Supabase) esté expuesto en código o en el historial de git.
- Si algún secreto se filtró alguna vez, rotarlo — borrarlo del código no lo borra del historial de git.
- Auditoría 2026-07-06 confirmó (leyendo variables reales vía CLI de Railway, solo lectura) que producción tiene configuradas claves reales de OpenAI, Groq, Qdrant, Supabase, JWT y WhatsApp — no placeholders. Al listarlas, el CLI las mostró en texto plano en la sesión de terminal: evitar pegar el output completo de `railway variables --json` en documentos versionados o compartidos; si una sesión con esos valores queda expuesta a alguien fuera de confianza, rotar las claves por precaución.
- La misma auditoría encontró dos variables reales en producción que no se usan en ningún lado del código actual: `SECRET_KEY` (no aparece declarada en `config.py` ni referenciada en `src/`) y `DEFAULT_TENANT_ID` (declarada en `config.py` pero no consumida en `src/`). No es un riesgo activo hoy, pero es basura de configuración candidata a limpiar.
- **Verificación 2026-07-07: los tests de Qdrant NO están aislados de producción de forma estructural, solo por coincidencia de nombres.** `VectorService._create_client()` (`src/services/vector_service.py`) se conecta usando `QDRANT_MODE`/`QDRANT_URL`/`QDRANT_API_KEY` reales del entorno — no hay ningún override en `conftest.py` (el único que existe en la raíz solo agrega `src/` al path, no toca variables de Qdrant). `tests/test_knowledge.py` usa `VectorService.clear_collection()` (hace `delete_collection` + recrea la colección vacía) sobre nombres hardcodeados como `test_products`, `products_test` y `products_integration_test` — nunca sobre el tenant_id real de Eje Inmobiliario (`eae6b1d9-09c9-421e-82b8-750c68aed89d`), pero únicamente porque ningún test usa ese valor hoy. **Si un test futuro llegara a usar el tenant_id real (por error, copy-paste, o una fixture dinámica), no hay ninguna barrera que le impida borrar la colección real `products_eae6b1d9-...`.** De hecho, las colecciones huérfanas `test_products`/`products_test`/`products_integration_test` que existen hoy en el Qdrant Cloud de producción son evidencia de que la suite ya corrió alguna vez contra esas credenciales reales.
- [ ] **Tarea concreta:** agregar un guard en `conftest.py` que aborte la ejecución de la suite si `settings.QDRANT_MODE` no es `memory`/`local` (o si `QDRANT_URL` apunta a la instancia Cloud de producción), antes de que cualquier fixture llegue a instanciar `VectorService`. Barato de implementar, cierra la única brecha real encontrada en esta verificación.

## Integración continua (CI)

- **No existe CI** (`.github/workflows` no existe), confirmado por auditoría 2026-07-06, pese a que hay una suite amplia de tests con pytest en `tests/` (~70 archivos). Nada corre esos tests automáticamente en un PR hoy — así fue como el bug de C07 (ver `spec/00-auditoria-y-plan-2026-07.md` sección 1) vivió semanas en una rama sin detectarse antes de mergear.
- Plan mínimo ya definido en la Fase E del plan de auditoría: agregar `.github/workflows/tests.yml` que corra `pytest` en cada push/PR contra `main`. Queda pendiente decidir si se adelanta en el orden de prioridad dado el costo bajo y el precedente de C07, o se deja para después de las Fases A–D como estaba planeado originalmente.

## Costos y abuso

- Rate limiting básico en endpoints que disparan llamadas a OpenAI, para evitar que un loop de conversación o un ataque simple genere un gasto descontrolado (por ejemplo, con `slowapi`).

## Hallazgos de la prueba real de WhatsApp (2026-07-07, sin resolver salvo donde se indica)

- **Mensajes duplicados: el handler de respuesta (`agent.reply.requested` → `src/services/agent_reply_handler.py::handle_agent_reply`) se ejecutó dos veces para un mismo mensaje de entrada, sin que el event bus (`src/core/event_bus.py`) mostrara doble suscripción ni el payload de Meta viniera duplicado.** Causa raíz no identificada tras búsqueda exhaustiva por código (ver [07-investigacion-mensajes-duplicados-2026-07-07.md](./07-investigacion-mensajes-duplicados-2026-07-07.md) sección 3). Mitigado con un guard de idempotencia a nivel de base de datos (`message_jobs.replied_at`, reclamo atómico), en rama `fix/duplicate-reply-guard`, pendiente de mergear. Nota arquitectónica de fondo, independiente de si se encuentra la causa exacta: el `worker_loop` y `handle_agent_reply` corren sobre el mismo proceso asyncio de un solo hilo (`asyncio.create_task` en `src/http/app.py`), y varias llamadas dentro de funciones `async def` (Supabase vía `supabase-py`, Qdrant, a veces OpenAI) son en realidad síncronas/bloqueantes — bloquean todo el event loop mientras corren. Esto no se ha confirmado como la causa de la duplicación, pero es una fragilidad real del diseño que vale la pena revisar en la Fase 2 (mover llamadas bloqueantes a un executor, o migrar a clientes async).

- **Sin validación de antigüedad de los datos del catálogo.** Grep en `src/services/rag_system.py` y `src/services/knowledge_base.py` por `created_at`/`updated_at`/`fecha`/`stale`/`expir`: cero resultados. Celeste confía ciegamente en lo que devuelva Qdrant, sin importar cuándo se cargó — el payload de los puntos ni siquiera tiene un campo de fecha (`text`, `precio`, `barrio`, etc., pero nada tipo `loaded_at`). Confirmado con las 6 propiedades reales de `products_eae6b1d9-...`, cargadas hace ~2 meses y usadas por el agente como si fueran del inventario actual.
- **El escalamiento a asesor humano solo funciona por palabra clave explícita — el criterio de "4 turnos sin resolución" es aspiracional, no está implementado.** El único mecanismo real de escalamiento (C06, `src/services/agent_orchestrator.py::_should_escalate`, líneas 343-359) evalúa exclusivamente si el mensaje contiene alguna de las `ESCALATION_KEYWORDS` (`"hablar con alguien"`, `"representante"`, `"comunicarme con"`, etc.) — la función ni siquiera recibe el historial de conversación como parámetro, solo el mensaje actual y el intent. La frase "La conversación lleva más de 4 turnos sin resolución" (`src/services/rag_system.py:521`) vive únicamente en el texto del system prompt enviado al LLM — si el modelo "decide" escalar en el texto de su respuesta, eso no dispara `_handle_escalation`/`_notify_owner`, así que el dueño real nunca se entera. Además, `ConversationContext.message_count` (`src/services/context_manager.py:81`, se incrementa en línea 221) sí existe pero no se conecta a ninguna lógica de escalamiento, y de todas formas se reinicia en cada mensaje porque `AgentOrchestrator`/`AdvancedContextManager` se recrean desde cero por cada mensaje procesado (visible en los logs: "AdvancedContextManager inicializado" aparece fresco en cada uno de los mensajes de la prueba). Confirmado en vivo: 4 mensajes seguidos de confusión ("no entiendo", "que me puedes ofrecer?", etc.) sin ninguna de las keywords, y el agente nunca escaló.

---
→ Siguiente: [03-seguridad-escalamiento.md](./03-seguridad-escalamiento.md)
