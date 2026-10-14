← [Índice](./README.md) · ← [01-produccion-mvp.md](./01-produccion-mvp.md)

# Investigación: mensajes duplicados y contradicción del P0 de cola — 2026-07-07

**Fecha de la investigación:** 2026-07-07
**Rama de trabajo:** `fix/duplicate-reply-guard` (creada desde `main` actualizado, commit `66e90d0`)
**Estado al cierre de esta sesión:** fix del problema #1 implementado y probado en la rama, **sin mergear**. Migraciones `017` y `018` escritas y aprobadas en contenido, **sin correr contra producción**. Problemas #2 y #3 (abajo) **sin investigar**.

**Actualización 2026-07-07 (sesión posterior):** se investigó a fondo el sospechoso de asyncio dejado abierto en la sección 3.3 y se agregaron tres cambios más a esta misma rama (claim atómico del worker, flag `WORKER_ENABLED`, columna `replied_by`). Ver sección 3.7 y 3.8.

> Este documento existe para que una sesión futura pueda retomar el trabajo sin releer todo el historial de chat. Si vas a continuar esto, empieza leyendo la sección "Qué hacer al retomar" al final.

---

## 1. Contexto: de dónde viene esto

`spec/01-produccion-mvp.md` punto 5 documentaba un hallazgo llamado "P0 — Pérdida silenciosa de mensajes en la cola", basado en una prueba real de WhatsApp del 2026-07-07 (madrugada, ~01:21-01:35 UTC): de 7 mensajes recibidos, 4 quedaban "encolados pero nunca procesados" según lectura de logs de Railway. Ese hallazgo motivó esta sesión de investigación.

## 2. Parte 1 — La contradicción del P0 (RESUELTA: el P0 original era falso)

### 2.1 El hallazgo contradictorio

Revisando Supabase directamente, se encontró que uno de los 4 wamid marcados como "nunca procesado" (`3EB0A41530...`) en realidad tenía `status=done`, `attempts=1`, sin error. Esto contradecía la conclusión original.

### 2.2 Metodología de verificación

Todo se verificó con evidencia directa, no releyendo memoria:

1. **Decodificación de los wamid completos.** Los wamid de WhatsApp vienen en formato `wamid.<base64>`; decodificando el base64 se obtiene un ID legible más un número de teléfono. Se usó esto para confirmar que los fragmentos cortos que se venían usando ("3EB0A41530", "AC15F4D3", etc.) correspondían exactamente a los mensajes reales, y se encontró que uno de los 4 fragmentos originales (`3EB0EE0003`) tenía un **error de transcripción** — el ID real es `3EB0EE0035EFBF2C3C1B59` (dígitos `0035` mal copiados como `0003`).

2. **Logs de Railway** (`railway logs --since ... --until ...` o el MCP `mcp__railway__get_logs`, deployment `dc85defe`, commit `66e90d0`) para reconstruir el rastro completo de cada mensaje: encolado (`[QUEUE] Job encolado`) → recogido por el worker (`[WORKER] N jobs pendientes` → `[WORKER] Job <id> completado`) → procesado por el agente (`[AGENT] Procesando mensaje...` → `[AGENT] Respuesta enviada...`).

3. **Consultas directas a Supabase (producción)** vía la API REST de PostgREST con `curl`, usando `railway run bash <script>` para inyectar `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` como variables de entorno **sin que sus valores crudos aparezcan nunca en el texto de un comando ni en la salida capturada** (ver `feedback_secrets_handling` en la memoria de sesiones — nunca pegar secretos crudos en comandos). Se consultaron las tablas `message_jobs` (status, attempts, last_error, created_at, processed_at) y `messages` (para ver qué le llegó realmente al cliente).

### 2.3 Resultado: los 4 mensajes SÍ se procesaron correctamente

Para los 4 wamid originalmente marcados como perdidos:

| wamid (fragmento) | status | attempts | last_error | Resultado real |
|---|---|---|---|---|
| `3EB0A41530...` ("Quiero reservar una propiedad") | done | 1 | null | Intent clasificado, RAG encontró propiedades, **reserva C07 creada** (`local los angeles`, 24h), LLM generó respuesta, WhatsApp enviado a las 01:22:19 UTC |
| `AC15F4D3...` ("Casa de alcázares") | done | 1 | null | Procesado y respondido en 1.4s |
| `ACF478B7...` ("Me interesa la casa de alcazares") | done | 1 | null | Procesado y respondido en 1.1s |
| `3EB0EE0035...` (typo del original) | done | 1 | null | Procesado y respondido en 1.9s |

Se confirmó además, leyendo la tabla `messages`, que el bot efectivamente mandó una respuesta de texto real al cliente en cada caso (no solo que el job se marcó `done`).

**Conclusión: el hallazgo P0 "pérdida silenciosa de mensajes en la cola" de `spec/01-produccion-mvp.md` punto 5 es incorrecto y debe darse por descartado.** La causa más probable del error original es que alguien buscó únicamente logs `[WORKER] Error` / `FAILED` en un volcado de ~5000 líneas y no encontró el log de éxito que sí existía, o usó fragmentos de wamid mal transcritos para buscar en Supabase (ver 2.2.1) y no encontró las filas por eso, no porque no existieran.

**Nota metodológica para el futuro:** durante esta misma investigación se llegó a una conclusión intermedia igual de incorrecta — que el worker loop había estado "colgado 13 minutos" — basada en un volcado de logs de Railway que resultó estar truncado/incompleto. Esa teoría se descartó al consultar Supabase directamente y ver que los jobs se habían procesado en 1-2 segundos, no en 13 minutos. **Lección: los logs de Railway obtenidos por rango de tiempo pueden venir incompletos sin ningún aviso de truncamiento — para conclusiones importantes, siempre cruzar con una consulta directa a la base de datos antes de afirmar algo basado solo en logs.**

### 2.4 Bug real (distinto) encontrado de paso

Durante esta parte de la investigación, aunque el pipeline funcionó de punta a punta, se notó una incoherencia: el primer mensaje ("Quiero reservar una propiedad") hizo que el RAG mencionara "casa alcazares" como una de 3 propiedades relevantes (score 0.45), pero cuando el cliente preguntó específicamente por ella poco después, el bot respondió "Actualmente no tengo esa propiedad". Esto es la primera señal del problema #2 documentado más abajo (sección 4).

---

## 3. Parte 2 — Mensajes duplicados (INVESTIGADO A FONDO, causa raíz NO encontrada, mitigación implementada)

### 3.1 El síntoma, reportado por prueba real de WhatsApp

Prueba real el 2026-07-07, 14:50-14:55 hora Bogotá (19:50-19:55 UTC), conversación real con el bot de Eje Inmobiliario. Dos incidentes de mensajes dobles:

**Incidente A** — después de que el cliente escribiera "perfecto gracias." (19:51:31.674 UTC), el bot mandó dos respuestas de despedida distintas, 327ms aparte:
- 19:51:34.225 — *"Con gusto 😊 Si en algún momento buscas propiedad en Manizales, aquí estaré. ¡Que tengas un buen día!"*
- 19:51:34.552 — *"Entiendo, no hay problema. Si en algún momento buscas propiedad en Manizales, aquí estaré 😊"*

**Incidente B** — después de "si claro es que no entiendo tu conversación" (19:52:14.795 UTC), dos respuestas de "no entiendo" distintas, 236ms aparte:
- 19:52:17.694 — *"Déjame ayudarte. ¿Qué tipo de propiedad estás buscando?..."*
- 19:52:17.930 — *"¿Podrías darme más detalles sobre lo que necesitas?..."*

Confirmado directamente en la tabla `messages` de Supabase (no es un artefacto de la app de WhatsApp): son 2 filas reales, ambas `sender=bot`, para cada incidente.

### 3.2 Lo que se descartó (con evidencia, no por intuición)

| Hipótesis | Cómo se descartó |
|---|---|
| Dos réplicas del servidor corriendo a la vez | `railway status --json` confirma `numReplicas: 1`, una sola instancia (`ad3c32ac-...`) en producción |
| Dos suscriptores escuchando el evento `agent.reply.requested` | El log `src.core.event_bus:publish` imprime `"Publicando 'agent.reply.requested' a 1 suscriptores"` en TODOS los casos revisados. Además, en todo `src/` solo hay **un** `event_bus.subscribe("agent.reply.requested", ...)` (antes en `src/http/app.py`, ahora en `src/services/agent_reply_handler.py`) |
| Meta (WhatsApp) mandó el mismo mensaje duplicado | El payload crudo guardado en `message_jobs.payload` para los jobs de los incidentes A y B contiene el mensaje del cliente **una sola vez** cada uno — no hay duplicación en el payload de entrada |
| Un segundo job en `message_jobs` para el mismo mensaje | Cada mensaje real del cliente en esa ventana tiene exactamente **una** fila en `message_jobs`, `attempts=1` |
| Un mecanismo de timeout/watchdog que manda una respuesta de repuesto si el pipeline tarda | Búsqueda exhaustiva en todo `src/` de `wait_for`, `TimeoutError`, `watchdog`, `fallback_reply`, `asyncio.wait(`, `.cancel()`, `asyncio.shield` — **cero resultados**. No existe ese mecanismo en el código |
| Una respuesta manual desde el dashboard (agente humano) se solapó | Ese endpoint (`POST /conversations/{id}/messages`, `src/http/routers/conversations.py`) requiere que el bot esté **desactivado** (409 si está activo) y persiste con `sender="agent"`, no `sender="bot"`. Las filas duplicadas son ambas `sender="bot"` |
| Código "bridge" viejo (`src/integrations/whatsapp_agent_bridge.py`) o `AgentOrchestrator.process_batch()` disparando una segunda respuesta | Ambos confirmados como código muerto: cero referencias a `WhatsAppAgentBridge(` ni a `process_batch(` en todo `src/` fuera de sus propias definiciones |

### 3.3 La pista real que sí se encontró (pero no llevó a la causa raíz)

En `src/services/response_generator.py`, el método `_generate_fallback()` (usado cuando el intent no matchea ninguna categoría específica) elige una frase al azar de una lista de 3:

```python
def _generate_fallback(self) -> str:
    fallbacks = [
        "No estoy seguro de entender. ¿Podrías reformular tu pregunta?",
        "¿Podrías darme más detalles sobre lo que necesitas?",
        "Déjame ayudarte. ¿Qué tipo de propiedad estás buscando?",
    ]
    return random.choice(fallbacks)
```

**Las dos respuestas del Incidente B son, literalmente, dos elecciones distintas de esa misma lista de 3.** Eso solo puede pasar si `response_generator.generate()` — y por lo tanto `agent_orchestrator.process_message()` completo — se ejecutó **dos veces** para el mismo mensaje de entrada (cada llamada a `random.choice` da un resultado independiente).

Sin embargo, revisando los logs de Railway del mismo tramo, **solo aparece un rastro completo del pipeline** por incidente (una sola clasificación de intent, una sola búsqueda RAG, una sola llamada al LLM, un solo log `[AGENT] Respuesta enviada` con el SUCCESS). La segunda respuesta no deja ningún rastro en las líneas de log instrumentadas del pipeline — aparece sin que se pueda ver de dónde salió.

**Conclusión honesta: no se identificó el mecanismo exacto que hace que el pipeline se ejecute dos veces.** Se agotaron las rutas de búsqueda razonables por código (ver tabla 3.2) sin encontrar un segundo disparador. Es posible que sea algo relacionado con el manejo interno de tareas asíncronas de Python (`asyncio.create_task` en `src/core/event_bus.py::publish`) que no deja huella textual buscable con grep — pero esto es una hipótesis sin confirmar, no un hallazgo.

### 3.4 Decisión: proteger al cliente sin depender de encontrar la causa raíz

En vez de seguir cazando la causa en frío, se implementó un **guard de idempotencia** que garantiza que, sin importar cuántas veces se dispare el pipeline internamente, el cliente reciba como máximo una respuesta por mensaje real. Adicionalmente, el guard deja un log explícito (`[GUARD]`) que servirá de evidencia la próxima vez que esto ocurra en producción — algo que hoy no existe.

#### Diseño

- **Llave de deduplicación:** `whatsapp_message_id` (el wamid completo), no el `job_id` de `message_jobs` — porque un solo job podría en teoría traer más de un mensaje en su payload (aunque no se ha observado en la práctica), y `job_id` habría bloqueado incorrectamente un segundo mensaje real en ese caso.
- **Mecanismo:** `UPDATE` condicional en base de datos, no un lock en memoria — un lock en memoria no sobrevive un restart/redeploy (y ya se sabe, por el caso del bug C07, que los redeploys ocurren con frecuencia en este proyecto), y no sería correcto si algún día el servicio escala a más de una réplica.
- **Dónde se reclama:** al principio de `handle_agent_reply`, **antes** de cargar el contexto del tenant y **antes** de llamar al orquestador del agente — para no gastar una llamada completa a OpenAI (costo + latencia) en una ejecución que de todos modos se va a descartar.

#### Archivos modificados/creados (en la rama `fix/duplicate-reply-guard`)

| Archivo | Cambio |
|---|---|
| `sql/migrations/017_add_replied_at_message_jobs.sql` | **Nuevo.** Agrega `message_jobs.replied_at TIMESTAMPTZ` (nullable) + índice parcial `idx_message_jobs_replied_at` sobre `whatsapp_message_id WHERE replied_at IS NULL`. 100% aditivo (`ADD COLUMN IF NOT EXISTS`), no toca datos existentes. **Aprobada en contenido por el usuario, pero NO ejecutada contra producción todavía.** |
| `src/services/agent_reply_handler.py` | **Nuevo.** `handle_agent_reply(event)` y `_resolve_conversation_id(...)` extraídos de `src/http/app.py` (antes vivían como función anidada dentro de `create_app().startup_event`, no importable ni testeable). Nueva función `_claim_reply(whatsapp_message_id, db_client)`: hace `UPDATE message_jobs SET replied_at=now() WHERE whatsapp_message_id=? AND replied_at IS NULL`; devuelve `True` si esta llamada ganó el reclamo (el `.data` de la respuesta viene no vacío), `False` si alguien ya lo reclamó antes. Si `whatsapp_message_id` viene vacío, deja pasar (no se puede deduplicar sin id, y no se quiere bloquear un flujo legítimo). Cuando bloquea, loguea `logger.warning(f"[GUARD] Envío duplicado bloqueado para whatsapp_message_id={whatsapp_message_id}")`. |
| `src/core/whatsapp_handler.py` | En `_dispatch_agent_events`, se agregó `"message_id": payload["message_id"]` al diccionario de datos del evento `agent.reply.requested` (antes no viajaba ese dato, y el guard lo necesita). |
| `src/http/app.py` | Se eliminaron ~171 líneas (la función anidada `handle_agent_reply` + `_resolve_conversation_id`); ahora el `startup_event` solo hace `from src.services.agent_reply_handler import handle_agent_reply` y `event_bus.subscribe(...)`. |
| `tests/test_agent_reply_handler.py` | **Nuevo.** Ver sección 3.5. |

#### 3.5 Tests (TDD, RED → GREEN confirmado sobre código real, no solo simulado)

Cuatro tests permanentes:

1. `test_sin_guard_dos_llamadas_concurrentes_mandan_dos_mensajes` — caracterización del bug: con `_claim_reply` forzado a `return True` siempre (equivalente a "sin guard"), dos llamadas concurrentes (`asyncio.gather`) a `handle_agent_reply` con el mismo `whatsapp_message_id` sí mandan 2 mensajes por WhatsApp. Sirve de regresión permanente que documenta que la condición de carrera es real.
2. `test_guard_bloquea_segundo_envio_duplicado` — con el guard real activo, las mismas 2 llamadas concurrentes solo mandan 1 mensaje, y se verifica que `logger.warning` se llamó con el texto `[GUARD] Envío duplicado bloqueado` incluyendo el `whatsapp_message_id`.
3. `test_claim_reply_gana_el_primero_y_bloquea_el_segundo` — unitario de `_claim_reply` sola.
4. `test_claim_reply_sin_message_id_no_bloquea` — caso borde: sin id, no bloquea.

**Demostración adicional en vivo** (no solo los tests permanentes): se deshabilitó temporalmente el guard directamente en `src/services/agent_reply_handler.py` (cambiando la condición a `if False:`), se corrió `test_guard_bloquea_segundo_envio_duplicado` → **falló** (`assert 2 == 1`, RED confirmado sobre el código real, no una simulación aparte). Se restauró el guard, se verificó con `diff` que el archivo quedó idéntico al original, se corrió de nuevo → **pasó** (GREEN).

**Regresión:** se corrieron 71 tests relevantes (`test_event_bus.py`, `test_whatsapp.py`, `test_whatsapp_integration.py`, `test_orchestrator.py`, `test_agent_edge_cases.py`, `test_agent_config_endpoint.py`, `test_agent_reply_handler.py`): 70 pasan, 1 falla (`test_orchestrator.py::TestStatistics::test_stats_track_workflows`) — confirmado con `git stash` que esa falla **ya existía en `main` sin tocar**, es un bug preexistente y no relacionado en `src/plugins/orchestrator.py` (el orquestador del sistema de plugins genérico, no el agente de IA).

### 3.6 ⚠️ Advertencia de orden de despliegue (crítica)

**Las migraciones `017` y `018` deben aplicarse en producción ANTES de desplegar este código.** Si el código llega a producción sin las columnas `replied_at`/`replied_by`, cada llamada a `_claim_reply` va a lanzar una excepción ("columna no existe"), que cae en el `except Exception` general de `handle_agent_reply` y se traga en silencio (solo un log `[AGENT] Error procesando agent reply: ...`). El resultado sería que **el agente deja de responder absolutamente nada por WhatsApp** — un problema mucho peor que los mensajes duplicados que se está intentando arreglar. Antes de mergear esta rama: correr ambas migraciones, confirmarlas, y solo después desplegar el código.

### 3.7 Investigación de seguimiento (sesión posterior 2026-07-07): descartando asyncio como causa intra-proceso

Se retomó explícitamente el sospechoso dejado abierto en 3.3 ("¿podría `asyncio.create_task` en `event_bus.py::publish` ejecutar el pipeline dos veces dentro del mismo proceso, sin dejar huella textual?"). Metodología: se enumeraron todas las rutas por las que un solo proceso asyncio podría disparar `agent_orchestrator.process_message` dos veces para el mismo mensaje, y cada una se contrastó con evidencia fresca (no releída) de logs de Railway del deployment `dc85defe` y de la documentación oficial de Railway.

**Rutas descartadas, con evidencia:**

| Hipótesis intra-proceso | Evidencia que la descarta |
|---|---|
| `handle_agent_reply` suscrito dos veces (`startup_event` corrido dos veces) | El log de `event_bus.publish` en el incidente A dice literalmente `a 1 suscriptores`. En el código de producción (`66e90d0`) hay un solo `event_bus.subscribe("agent.reply.requested", ...)`. |
| Dos `worker_loop()` corriendo en el mismo proceso | Un solo banner `✅ Worker loop iniciado` en todo el deployment (00:51:00 UTC, una sola vez). Además, entre el `SELECT status='pending'` y el `UPDATE status='processing'` del worker no hay ningún `await` real — todas las llamadas a Supabase son síncronas/bloqueantes — así que el event loop no puede ceder el control a otra task en esa ventana; no hay punto de intercalado posible aunque hubiera dos loops. |
| Un solo `publish()` crea dos `asyncio.create_task` para el mismo evento | El código de `EventBus.publish` itera una vez por suscriptor y crea una task por iteración; con 1 suscriptor, es 1 task. No hay bifurcación posible. |
| Retry del job por error posterior al dispatch | Requeriría `attempts=2`; los jobs de ambos incidentes tienen `attempts=1`. |

**Evidencia decisiva — la ventana completa de logs del incidente A (19:51:25–19:51:45 UTC) se pidió de nuevo, con cuidado de que viniera contigua (lección de la sección 2.3):** el volcado muestra, sin huecos, 1 job encolado → 1 `[WORKER] Job … completado` → 1 `📢 Publicando 'agent.reply.requested' a 1 suscriptores` → el pipeline completo de intent/RAG/LLM una sola vez → 1 `[AGENT] Respuesta enviada a 573152172817: Con gusto 😊…` (el texto de la **primera** respuesta del incidente). El texto de la segunda respuesta ("Entiendo, no hay problema…") **no aparece en ningún punto de ese stream** — ni antes, ni después, ni intercalado. Si el pipeline se hubiera ejecutado dos veces en el mismo proceso, las ~40 líneas DEBUG de la segunda ejecución tendrían que estar en ese mismo lote de logs. **Conclusión: la causa NO es intra-proceso.** El sospechoso de asyncio queda descartado.

**Evidencia adicional confirmada — patrón de fase de los timestamps (no solo "existen dos respuestas"):** el offset entre las dos respuestas de cada incidente **no es constante ni casi-cero**, y decrece de un incidente al siguiente:
- Incidente A (19:51:34.225 / 19:51:34.552): **327 ms**
- Incidente B (19:52:17.694 / 19:52:17.930): **236 ms**

Un solo proceso disparando dos veces la misma llamada (p.ej. un bug de doble-await o un handler suscrito dos veces) produciría un offset mínimo y aproximadamente constante — las dos ejecuciones arrancarían prácticamente en el mismo instante de wall-clock. Un offset que además **cambia** de un incidente a otro es la firma esperada de **dos procesos con loops independientes de ~2 segundos** (el worker loop duerme `asyncio.sleep(2)`) que arrancaron en momentos ligeramente distintos y van derivando en fase entre sí — cada uno reclama y procesa el mismo job pendiente con un desfase que depende de en qué punto de su propio ciclo de 2s se encontraba cuando llegó el mensaje. Esto es evidencia real tomada de los logs, no una inferencia — lo que sigue sin confirmarse es el origen exacto del segundo proceso.

**Hipótesis fuerte (NO confirmada con prueba directa de origen):** un segundo proceso corriendo *fuera* de Railway — muy probablemente un `uvicorn --reload` local, dado que el historial de PowerShell de la máquina de desarrollo registra 67 invocaciones de `python -m uvicorn src.http.app:app ... --reload` — con el `.env` local apuntando al mismo proyecto de Supabase de producción (`SUPABASE_URL=https://qradxebxvmliyhmusavq.supabase.co`, confirmado; no se imprimieron claves). Esto convierte a cualquier proceso local en, funcionalmente, una segunda réplica del worker compitiendo por `message_jobs` contra el proceso de Railway. Combinado con que el claim `pending→processing` no era atómico (ver 3.4), ambos procesos podían leer y procesar el mismo job.

**Lo que falta para pasar de "hipótesis fuerte" a "confirmado":** no se tuvo acceso a logs de la API de Supabase (IP de origen de los requests a `message_jobs`/`messages` en la ventana del incidente) ni se pudo confirmar directamente que había un proceso local corriendo a las 14:51-14:52 hora Bogotá del 2026-07-07. Revisar esto es el primer paso si se retoma la búsqueda de la causa raíz exacta.

### 3.8 Mitigaciones agregadas en esta sesión (independientes de si la hipótesis anterior es la causa exacta)

Se implementaron tres cambios adicionales sobre `fix/duplicate-reply-guard`, con TDD, sin tocar la migración `017` (ya aprobada):

1. **Claim atómico del worker** (`src/services/message_worker.py::_process_job`): el `UPDATE ... SET status='processing'` ahora incluye `.eq("status", "pending")` en el filtro. Si el job ya no estaba `pending` (otro proceso ganó la carrera), `result.data` viene vacío, se loguea `[WORKER] Job {id} ya reclamado por otro proceso` y se sale sin excepción ni reintento. Antes, el `UPDATE` no verificaba el estado previo, así que dos procesos leyendo el mismo job pendiente podían procesarlo ambos.
2. **Flag `WORKER_ENABLED`** (`src/services/message_worker.py::should_run_worker`, usado en `src/http/app.py::startup_event`): el worker loop ya no arranca automáticamente en cualquier proceso. `WORKER_ENABLED=true`/`false` explícito manda siempre; si no está seteado, el default es correr solo si se detecta al menos una de tres variables que Railway documenta como siempre inyectadas a un deployment (`docs.railway.com/variables/reference`, consultado en esta sesión): `RAILWAY_ENVIRONMENT_NAME`, `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`. Se usan las tres (no una sola) porque `RAILWAY_ENVIRONMENT` (sin sufijo `_NAME`) — el nombre que se iba a usar inicialmente por intuición — **no aparece en la documentación vigente de Railway** (era el nombre de Railway v1); depender de una sola variable no confirmada habría arriesgado que el worker no arrancara en producción, un problema estrictamente peor que el bug original. El arranque (o no) queda logueado sin ambigüedad: `✅ Worker loop iniciado` o `⚠️ Worker loop deshabilitado`.
3. **Columna `replied_by`** (`sql/migrations/018_add_replied_by_message_jobs.sql`, nueva migración — la `017` queda intacta): guarda `hostname:pid` (`src/core/process_identity.py::get_process_identity`), escrito tanto por el claim atómico del worker como por `_claim_reply` en `agent_reply_handler.py`. Bajo el invariante de que el claim del worker ahora es atómico, ambos claims para un mismo mensaje siempre los debería ganar el mismo proceso (porque solo el proceso que ganó `pending→processing` llega a publicar el evento que dispara `_claim_reply` en su propio event loop); si alguna vez aparece un `replied_by` que no cuadra con lo esperado, es evidencia directa de una colisión de procesos.

**Regresión:** 80 passed / 1 failed / 8 skipped en el mismo subset de archivos que se usó en la sesión anterior (`test_event_bus.py`, `test_whatsapp.py`, `test_whatsapp_integration.py`, `test_orchestrator.py`, `test_agent_edge_cases.py`, `test_agent_config_endpoint.py`, `test_agent_reply_handler.py`) más los tests nuevos (`test_message_worker.py`, `test_process_identity.py`). La única falla sigue siendo `test_orchestrator.py::TestStatistics::test_stats_track_workflows` — confirmada nuevamente como preexistente y no relacionada (pasa aislada; pertenece a `src/plugins/orchestrator.py`, el orquestador genérico de plugins, no al agente de IA). La suite completa (`pytest` sin filtrar) tiene además 14 fallas en `test_cache.py`, `test_generator.py`, `test_integration_advanced.py` y `test_knowledge.py` — ninguno de esos archivos importa nada de `message_worker.py`, `agent_reply_handler.py`, `whatsapp_handler.py` ni `app.py` (verificado por grep de imports), consistente con que sean fallas ambientales preexistentes (dependen de `cache_service`, `embedding_service`/`vector_service`/`knowledge_base`/`rag_system` con red/modelos reales) fuera del alcance de esta rama.

---

## 4. Problema #2 — SIN INVESTIGAR: el bot pierde el contexto de qué propiedad se está discutiendo

Reportado en la misma prueba del 2026-07-07 (14:50-14:55 Bogotá): el cliente preguntó por "casa de alcázares" — propiedad que el bot **ya le había mostrado dos veces antes en la misma conversación** — y el bot respondió *"No encontré propiedades exactas, pero déjame buscar alternativas."*

Esto es consistente con el bug menor ya notado en la sección 2.4 (el bot dijo "no tengo esa propiedad" para algo que sí tenía, en otro momento de la misma sesión de pruebas).

**Hipótesis a verificar (sin confirmar todavía):** ¿el RAG (`src/services/rag_system.py` / `src/services/knowledge_base.py`) recibe el nombre de la propiedad mencionada como parte del contexto de la pregunta de seguimiento, o cada mensaje se busca de forma aislada (solo el texto literal del último mensaje, sin memoria de qué producto está en discusión)? Revisar especialmente `agent_orchestrator.py::process_message` pasos 5 y 7 (búsqueda RAG y mejora con LLM) y cómo se arma el `query` que se le pasa a `rag_system.kb.search_products` / `generate_with_context` — si solo se usa `message` (el texto crudo del último mensaje del cliente) sin enriquecerlo con el nombre de producto ya mencionado en `context.mentioned_products` (ver `context_manager.py`), ahí probablemente está el problema.

**No se investigó nada de esto todavía** — quedó pendiente porque la prioridad acordada con el usuario fue resolver primero el problema #1 (mensajes duplicados, por ser "el más concreto y rápido de aislar con logs").

### 4.1 Actualización 2026-07-08 — investigación inicial (CAUSA IDENTIFICADA A NIVEL DE CÓDIGO, sin reproducir en vivo todavía)

Se verificaron primero las dos hipótesis alternas antes de mirar el código de `agent_orchestrator.py`:

1. **¿`tenant_id`/colección de Eje Inmobiliario mal configurado?** Descartado. Consulta directa a producción (Supabase, tabla `agent_config`, vía `railway run` para no exponer credenciales) confirma `tenant_id = eae6b1d9-09c9-421e-82b8-750c68aed89d` exacto, fila creada el 2026-05-15. La colección de Qdrant `products_eae6b1d9-09c9-421e-82b8-750c68aed89d` existe, `status=green`, **6 puntos** (propiedades) cargadas — no está vacía.
2. **¿`system_prompt` custom en conflicto con el prompt hardcodeado de Celeste (`rag_system.py::_build_system_prompt_inmobiliario`, fusionado en `bffec1e`)?** Descartado. `agent_config.system_prompt` para este tenant es `NULL` (nunca se ha hecho `PATCH /api/v1/agent/config` — `updated_at == created_at`). También `owner_phone` sigue `NULL` (tarea P0/P1 #6 de [[real-estate-tasks]] sigue pendiente — la escalación no notifica al asesor). El agente usa el prompt hardcodeado por defecto, no uno personalizado.

**Causa real, confirmada leyendo el código (no solo hipótesis):**

- `src/services/intent_classifier.py` sigue siendo la versión genérica de e-commerce (keywords de laptops, HP/Dell, "carrito", "factura" — ver [[real-estate-tasks]] tarea P1#4, sin hacer). **No existe ningún intent que distinga "quiero ver el catálogo en general" de "busco algo específico"** — ambos caen en `product_search` o `other`.
- `agent_orchestrator.py::_should_search_kb` (línea 508) dispara búsqueda vectorial en Qdrant para prácticamente cualquier intent (`product_search`, `product_info`, `price_inquiry`, `availability`, `purchase_intent`, `other`) — no hay una rama separada de "listar catálogo completo" sin pasar por similitud semántica.
- La búsqueda (línea 176-178) siempre usa `query=message` — el texto crudo del último mensaje — como embedding de búsqueda, sin importar si el mensaje es específico ("apartamento 2 habitaciones en X barrio") o genérico ("qué propiedades tienes", "muéstrame el catálogo").
- `knowledge_base.py::search_products` tiene `min_score=0.0` **hardcodeado**, con el comentario explícito en el código: `# Bajado a 0.0 para funcionar con mock embeddings` (línea 168) — es decir, un workaround de desarrollo con embeddings falsos que quedó activo en producción con embeddings reales. Esto significa que **cualquier mensaje, sin importar qué tan mal calce semánticamente, siempre devuelve hasta 5 resultados** como si fueran relevantes — no hay filtro de calidad de match.
- Con solo 6 propiedades cargadas en total y `limit=5`, una consulta genérica devuelve casi todo el catálogo, pero **cuál propiedad queda excluida del top-5 varía según la redacción exacta del mensaje genérico** (porque el ranking depende de un embedding de una frase genérica que no se parece semánticamente a ninguna descripción de propiedad en particular — el orden es esencialmente ruido). Esto es consistente con el síntoma ya observado en la sección 2.4 y el problema #2 original: el bot mencionó "casa alcázares" en una respuesta y poco después dijo "no tengo esa propiedad" — probablemente porque en ese segundo mensaje genérico la propiedad quedó fuera del top-5 semántico, no porque realmente no exista en el catálogo.

**Lo que falta para confirmar en vivo (no hecho todavía):** reproducir con una conversación real de WhatsApp una secuencia de "pregunta general → pregunta específica sobre algo mostrado antes" y confirmar en logs (`[AGENT] Propiedades encontradas`) que la propiedad esperada entra y sale del top-5 entre ambas llamadas. También falta decidir el fix (candidatos: subir `min_score` a un umbral real tipo 0.3-0.5 ahora que se usan embeddings reales, o distinguir intent de "listar todo" y en ese caso hacer `scroll` de la colección completa en vez de búsqueda semántica — dado que el catálogo es pequeño, hoy 6 propiedades).

## 5. Problema #3 — SIN INVESTIGAR: silencio de ~1 minuto antes de responder

Reportado en la misma prueba: ante el mensaje "aparta estudio" (con typo, probablemente por "apartaestudio"), el bot tardó aproximadamente 1 minuto en responder.

**Preguntas a resolver (sin investigar todavía):**
- ¿El mensaje se encoló con normalidad (`[QUEUE] Job encolado` inmediato tras la recepción del webhook)?
- Si se encoló rápido, ¿el worker tardó en recogerlo (`[WORKER] N jobs pendientes` tardío)?
- Si el worker lo recogió rápido, ¿la demora está dentro del pipeline del agente (búsqueda RAG lenta, llamada a OpenAI lenta, reintento de algún servicio externo)?

Dato de contexto que puede ser relevante: como se documentó en la sección 3, el worker loop y el manejo de eventos corren todos sobre el mismo proceso asyncio de un solo hilo, y varias llamadas (Supabase, Qdrant, OpenAI) son síncronas/bloqueantes dentro de funciones `async def` — cualquier llamada bloqueante que tarde más de lo normal (timeout de red, cold start de algún servicio) podría explicar un retraso visible como "silencio" sin que haya ningún error explícito. Esto es una hipótesis a favor de investigar, no una conclusión.

**No se investigó nada de esto todavía.**

---

## 6. Qué hacer al retomar este trabajo

En orden sugerido:

1. **Si la rama `fix/duplicate-reply-guard` todavía no se mergeó:** correr la migración `017_add_replied_at_message_jobs.sql` contra producción (mostrar el SQL primero, confirmar), verificar que la columna existe, y solo después mergear y desplegar. Confirmar en logs de Railway que el agente sigue respondiendo con normalidad tras el deploy (buscar `[AGENT] Respuesta enviada` en los minutos posteriores).
2. **Si en algún momento aparece un log `[GUARD] Envío duplicado bloqueado`** en producción: esa es la primera evidencia real de cuándo/bajo qué condiciones se dispara el problema #1 dos veces. Vale la pena correlacionar la hora exacta con el resto de logs de esa ventana (con más cuidado que en esta sesión — pedir el rango completo y verificar que no venga truncado, cruzando con Supabase si hay dudas) para retomar la búsqueda de la causa raíz con una pista real en vez de partir de cero.
3. **Investigar el problema #2** (sección 4) — probablemente el de mayor impacto en la calidad percibida del bot, ya que hace que Celeste se contradiga con el cliente dentro de la misma conversación.
4. **Investigar el problema #3** (sección 5) — usar la misma metodología de la sección 2: cruzar logs de Railway con consultas directas a `message_jobs`/`messages` en Supabase, no confiar en logs de rango de tiempo sin verificar que vinieron completos.

---
→ Relacionado: [01-produccion-mvp.md](./01-produccion-mvp.md) (punto 5, corregido) · [02-arquitectura-backend.md](./02-arquitectura-backend.md) (hallazgo arquitectónico del event bus)
