# Auditoría de ramas + plan de entorno de trabajo — julio 2026

**Fecha de la auditoría:** 2026-07-06
**Contexto:** Se pidió auditar el estado real de las ramas de git (no de memoria), preparar un espacio de trabajo óptimo, y confirmar si existe un entorno Railway separado para desarrollo vs. producción, para que el desorden actual no se repita. Corresponde a la Fase 0 de `spec/00-entorno-dev.md`, que este documento amplía con evidencia verificada.

Todo lo de abajo se verificó con comandos directos (`git fetch --all`, `git branch -vv`, `git log`, `git diff`, lectura de código en cada rama) — no se asumió nada de memorias previas. Donde la memoria previa decía algo distinto a lo encontrado, se marca explícitamente.

---

## 1. Hallazgo crítico: el bug NameError de C07 sigue vivo en producción

La memoria previa (`critical_bugs.md`) daba este bug por corregido en el commit `bffec1e`. **Eso es cierto solo dentro de la rama `fix/celeste-prompt-and-c07`** — nunca se mergeó a `main`.

Verificado directamente sobre `origin/main` (lo que Railway tiene desplegado hoy, según `spec/00-entorno-dev.md` que documenta que solo `main` está conectado a Railway):

```
git show origin/main:src/services/agent_orchestrator.py
```

Líneas 157–159 de `origin/main`:
```python
# ✅ C07: DETECTAR INTENCIÓN DE RESERVA
from src.services.reservation_service import detect_reservation_intent, create_reservation
if detect_reservation_intent(message) and rag_results:   # <- rag_results NO existe todavía aquí
```

`rag_results` recién se define en la línea 195 (`rag_results = []`), **36 líneas después** de usarse. Cualquier mensaje de WhatsApp real que contenga "apartar", "reservar" u otra palabra que dispare `detect_reservation_intent` provoca un `NameError`, capturado por el try/except externo, que responde con el mensaje genérico "tuve un problema procesando tu mensaje" en vez de la respuesta real.

**Esto está pasando ahora mismo en producción, no es un bug histórico.**

## 2. Estado real de cada rama (verificado, no inferido)

| Rama | Último commit | Fecha | Estado vs. `main` |
|---|---|---|---|
| `main` (checkout local) | `f395b9e` | — | **18 commits detrás** de `origin/main` — desactualizada, hay que hacer `git pull` antes de tocar nada |
| `origin/main` (lo que Railway despliega) | 18 commits adelante del local | — | **Tiene el bug C07 NameError activo.** Sí tiene ya el fix de amnesia UUID (`_resolve_conversation_id` en `app.py`), pero NO tiene el manejo 503 en `GET /agent/config` |
| `fix/celeste-prompt-and-c07` (rama de trabajo actual) | `bffec1e` | 2026-07-01 | Fix C07 correcto (bloque movido después de definir `rag_results`) + prompt inmobiliario "Celeste" fusionado + mejoras v2/v3 del RAG (clasificador de intención previo a Qdrant, score mínimo 0.3, historial limitado a 10 mensajes, logs `[INTENT]`). **Es la rama más completa y más nueva de las tres candidatas.** 0 commits detrás de main. |
| `origin/stephania-fix-celeste-agente` | `bd4abbd` | 2026-06-30 | También corrige C07 (commit `72095ff`: "mover bloque C07 al lugar correcto"), pero es un **snapshot anterior**: no tiene las mejoras v2/v3 que sí tiene `fix/celeste-prompt-and-c07`. Diff línea por línea confirma que no aporta nada que la otra rama no tenga ya — es candidata a cerrarse sin mergear. |
| `origin/development` | 4 commits adelante / 32 detrás de main | — | Los 3 commits de notificaciones (`Fix-Notificaciones no se refleja`, `Fix-Error de Notificaciones`, `feat(notifications)...`) ya están en `main` por otra vía (commits distintos, mismo resultado). El único valor real no cubierto en main: el manejo 503 del commit `522b316` en `GET /agent/config` (`src/http/routers/agent.py`, ~9 líneas: envolver `agent_config_repo.get_by_tenant_id()` en try/except y devolver 503 en vez de 500 crudo). La parte de "amnesia UUID" del mismo commit ya está resuelta en `main` de otra forma (`_resolve_conversation_id`). |

### Diff clave que confirma cuál prompt es el bueno

`git diff origin/fix/celeste-prompt-and-c07 origin/stephania-fix-celeste-agente -- src/services/rag_system.py` muestra que `stephania-fix-celeste-agente` **elimina** el clasificador de intención pre-Qdrant, el score mínimo 0.3, el límite de historial de 10 mensajes y los logs `[INTENT]` — es decir, es una versión anterior sin esas mejoras, no una alternativa con algo distinto que aportar.

## 3. Otros hallazgos de la auditoría

- **No hay `railway.json` ni `railway.toml`** en el repo, solo un `Procfile` simple (`web: uvicorn src.http.app:app --host 0.0.0.0 --port $PORT`). No hay evidencia en el código de un segundo entorno Railway — coincide con lo que ya documenta `spec/00-entorno-dev.md` sección 0.1, pero **no se pudo confirmar contra el dashboard real de Railway** (ver sección 5, bloqueo de acceso).
- **No existe CI** (`.github/workflows` no existe), pese a que hay una suite amplia de tests (~70 archivos en `tests/`, pytest). Nada corre esos tests automáticamente en un PR hoy — así es como un bug como el de C07 puede vivir semanas en una rama sin detectarse antes de mergear.
- Archivo basura en la raíz del repo: `s -ExecutionPolicy RemoteSigned) ; (& c...Activate.ps1)` (~12KB), generado por un comando de activación de venv mal pegado en la terminal. Candidato a borrar.
- Archivos sin trackear en el working tree: `docs/ARCHITECTURE.md`, `docs/CORE.md`, `docs/DEVELOPMENT_GUIDE.md`, `CLAUDEbackend.md`, la carpeta `spec/` completa — parecen trabajo en progreso propio, no se tocaron.
- `.gitignore` tiene cambios locales sin commitear (agrega `tree_snapshot.txt` y `contexto_estructuraai.md` a los ignorados).
- El emoji 💡 hardcodeado (`response_generator.py:361-362`) y el teléfono `3116457633` hardcodeado (4 veces en el system prompt de `rag_system.py`, no solo en `response_generator.py` como decía la memoria previa) siguen sin resolverse — ver `spec/01-produccion-mvp.md` punto 3.

## 4. Plan de 5 fases (aprobado en estructura, pendiente de ejecutar)

Orden recomendado: **A → B → C → D → E**. C requiere confirmación de Railway antes de continuar (ver bloqueo en sección 5).

### Fase A — Hotfix: sacar el bug vivo de producción (máxima prioridad)

**Ajustado 2026-07-06 al flujo de trabajo individual** (sin PR formal en GitHub, merge nunca rebase — ver `00-entorno-dev.md` sección 0.4):

1. Actualizar `main` local: `git checkout main && git pull origin main`.
2. Sobre `fix/celeste-prompt-and-c07` (rama actual, la más completa): traer los cambios de `main` con `git merge main` si hace falta (nunca rebase), correr tests relevantes (`pytest tests/test_orchestrator.py tests/test_agent_edge_cases.py tests/test_intent_classifier_enhanced.py` como mínimo) antes de tocar nada más.
3. Sumar el fix suelto del 503 en `GET /agent/config` (`src/http/routers/agent.py`, ~9 líneas, ver commit `522b316` de `development`) dentro de la misma rama, antes de mergear a `main` — única pieza de valor rescatable de esa rama.
4. Revisar el diff yo misma antes del merge: `git diff --stat main..fix/celeste-prompt-and-c07` primero, luego el diff completo — sin PR formal, esta revisión reemplaza esa función.
5. Merge local a `main`: `git checkout main` → `git merge fix/celeste-prompt-and-c07` → `git push origin main` → Railway autodespliega. Confirmar en logs de Railway que arrancó sin errores.
6. Prueba real: mensaje con "apartar"/"reservar" al WhatsApp conectado → confirmar que ya no cae en el mensaje de error genérico.
7. Borrar la rama `fix/celeste-prompt-and-c07` ya mergeada, local y remota.

### Fase B — Consolidar ramas (limpieza segura, reversible)

1. Antes de borrar nada, tags de respaldo:
   ```
   git tag archive/development origin/development
   git tag archive/stephania-fix-celeste-agente origin/stephania-fix-celeste-agente
   git push origin archive/development archive/stephania-fix-celeste-agente
   ```
2. **Punto de confirmación explícita antes de ejecutar** `git push origin --delete development stephania-fix-celeste-agente` (acción sobre remoto compartido, se confirma en el momento, no por aprobar este documento).
3. Limpiar tracking local: `git branch -d stephania-fix-celeste-agente`, `git remote prune origin`.
4. Borrar el archivo basura de la raíz.
5. Decidir versionado de `docs/ARCHITECTURE.md`, `docs/CORE.md`, `docs/DEVELOPMENT_GUIDE.md`, `CLAUDEbackend.md`, `spec/` — quedan como están por ahora.

### Fase C — Confirmar el entorno Railway real

1. Revisar el dashboard/API de Railway: ¿un solo servicio o dos? ¿variables reales de `LLM_PROVIDER`, `QDRANT_MODE`, `JWT_SECRET` en producción? (`.env` local está en `.gitignore`, no refleja producción).
2. Actualizar `spec/00-entorno-dev.md` sección 0.1 con el estado confirmado.
3. Recomendación (alineada con el spec existente): no crear un segundo servicio de staging todavía, siendo una sola developer — mantenerlo simple con buen flujo de rama+PR. Reconsiderar si el ritmo de clientes lo justifica.

### Fase D — Flujo de trabajo estándar (para que esto no vuelva a pasar)

Documentar en `spec/00-entorno-dev.md` (actualizando la sección 0.4 existente):
1. Ritual de inicio de sesión: `git fetch --all --prune` + `git branch -vv` + `git status` antes de tocar cualquier archivo.
2. Regla anti-duplicación de ramas: antes de crear una rama nueva sobre agente/prompt/orchestrator, correr `git branch -r` y confirmar que no hay otra rama abierta tocando lo mismo — esto es exactamente lo que generó las 2 ramas compitiendo por el mismo prompt.
3. Una rama = un merge en días, no semanas (sin PR formal, ver ajuste de flujo del 2026-07-06). Nada de ramas flotando sin mergear ni cerrar.
4. Borrar la rama remota inmediatamente después de mergear (`git push origin --delete rama`).
5. Checklist mínimo antes de mergear a `main`: tests relevantes pasan localmente, probado manualmente el flujo afectado, diff revisado con `--stat` primero y luego completo.
6. Mantener la mini-spec obligatoria para archivos de riesgo alto (system prompt, `agent_orchestrator.py`, `app.py`) que ya define el spec 0.4.

### Fase E — Salvaguarda barata: CI mínimo

1. Agregar `.github/workflows/tests.yml`: en cada push/PR contra `main`, instalar dependencias y correr `pytest`.
2. (Opcional, requiere permisos de admin de GitHub, fuera de mi alcance ejecutar): branch protection en `main` — exigir que el CI pase antes de mergear, bloquear push directo.

### Verificación end-to-end del plan

- Fase A: mensaje real de WhatsApp con intención de reserva → ya no responde con el mensaje de error genérico; logs de Railway sin excepción NameError.
- Fase B: `git branch -r` limpio, solo `main` y ramas activas; tags de respaldo visibles con `git tag -l "archive/*"`.
- Fase D/E: al abrir el próximo PR de prueba, el workflow de CI corre solo y reporta pass/fail en GitHub.

## 5. Railway: acceso resuelto y estado real confirmado (2026-07-06, actualizado)

El bloqueo de acceso descrito originalmente en esta sección **ya no aplica**. El CLI de Railway quedó vinculado al proyecto correcto: workspace `camiloo2525's Projects`, proyecto `refreshing-respect` (id `dedbda30-0507-4edb-bca0-a1be545736bd`), environment `production`, servicio `backEstructuraAI` (id `888112e6-8c6f-4ed9-b9e2-d3463a917a84`). Confirmado con `railway whoami --json` y `railway status --json`.

Todo lo siguiente se verificó en modo **solo lectura** (sin desplegar, redeployar, borrar ni modificar nada), respondiendo a las 4 preguntas que quedaban pendientes de la Fase C.

### 5.1 Servicios y entornos — corrige la sección 3

La sección 3 asumía que no había evidencia de un segundo entorno Railway. Eso era correcto respecto a archivos en el repo (no hay `railway.json`/`railway.toml`), pero **incompleto**: el proyecto sí tiene **dos entornos** para el mismo servicio `backEstructuraAI`, configurados directamente en la plataforma Railway (no como IaC versionado):

| Entorno | Rama auto-deploy | Dominio | Último deploy activo |
|---|---|---|---|
| `production` | `main` | `backestructuraai-production.up.railway.app` | commit `d30739e` "chore: clean deploy marker", 2026-05-30, status `SUCCESS` |
| `development` | `development` | `backestructuraai-development.up.railway.app` | commit `71a474d` "Fix-Notificaciones no se refleja", 2026-05-28, status `SUCCESS` |

No existe un tercer entorno ni un servicio de staging separado. El deploy activo de `development` es de 2026-05-28 — anterior a los commits recientes de fix de C07 en las ramas de trabajo (sección 2) — así que no refleja el estado actual de ninguna rama candidata sin revisarlo de nuevo.

### 5.2 Variables reales de producción

Listadas con `railway variables --service backEstructuraAI --environment production --json`. Confirmado (valores no reproducidos aquí a propósito, ver nota de seguridad):

- `LLM_PROVIDER=openai`, `LLM_FALLBACK_PROVIDER=groq`, `OPENAI_MODEL=gpt-4o-mini`, `GROQ_MODEL=llama-3.3-70b-versatile` — producción corre con OpenAI como proveedor principal y Groq como fallback real (claves con formato válido, no placeholders).
- `QDRANT_MODE=cloud`, `QDRANT_URL` apunta a una instancia real de Qdrant Cloud (`*.aws.cloud.qdrant.io`) con `QDRANT_API_KEY` en formato JWT real — no es el modo local/memoria.
- `JWT_SECRET` y `JWT_REFRESH_SECRET` están seteados con valores reales, no vacíos ni tipo "changeme".
- `SUPABASE_URL`/`SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_JWT_SECRET` apuntan a un proyecto Supabase real (`qradxebxvmliyhmusavq.supabase.co`).
- `WHATSAPP_TOKEN`, `WHATSAPP_TOKEN_EJE_INMOBILIARIO`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WHATSAPP_VERIFY_TOKEN` — valores reales de Meta; el WhatsApp conectado en producción es el del tenant `eje-inmobiliario` ("ESTRUCTURA TECH", número `+573124567890`).
- `ENVIRONMENT=production`, `DEBUG=false` — correctos.
- Dato llamativo, no bloqueante: `DEFAULT_TENANT_ID=tenant_dev` — producción sigue usando un ID de tenant por defecto que suena a "dev". Candidato a revisar aparte, fuera del alcance de las Fases A–E.

⚠️ **Nota de seguridad:** al listar variables, el CLI devolvió en texto plano los valores reales de `OPENAI_API_KEY`, `GROQ_API_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `QDRANT_API_KEY`, `WHATSAPP_TOKEN` y `WHATSAPP_TOKEN_EJE_INMOBILIARIO`. Por eso no se reproducen en este documento (que vive versionado en `spec/`). Quedaron expuestos en el output de la sesión de terminal de esta auditoría; si esa sesión o su historial se comparte con alguien fuera de confianza, conviene rotar esas claves por precaución.

### 5.3 Logs de producción: búsqueda del NameError de C07

Se descargaron ~5000 líneas de logs de `backEstructuraAI` en `production` (rango real cubierto: 2026-07-02 02:55 a 2026-07-06 20:29, ~4.5 días; el volumen está dominado por polling del dashboard cada minuto — `GET /api/v1/conversations`, refresh de tokens, etc.).

**No se encontró el `NameError` de C07 en esta ventana.** Tampoco hay evidencia de que el bloque "C07: DETECTAR INTENCIÓN DE RESERVA" se haya ejecutado en absoluto durante estos ~4.5 días: no aparecen logs de mensajes de WhatsApp entrantes ni de `agent_orchestrator` procesando texto de usuario, solo tráfico del dashboard autenticado. Lo único relacionado con "C07" en la ventana:

- `[C07] Error en release_expired_reservations: <ConnectionTerminated...>` (2026-07-05 02:02) — es el job que libera reservas expiradas (`release_expired_reservations`), una función distinta al bloque del `NameError`. No confirma ni descarta el bug.
- Dos tracebacks de `httpx.ReadError` en `POST /conversations/.../read` (2026-07-06 20:29) — error de red al marcar una conversación como leída, sin relación con C07.

**Conclusión:** el bug sigue confirmado por lectura directa del código fuente en `origin/main` (sección 1) — eso no cambia con esto. Lo que esta vuelta no pudo confirmar es verlo *disparar* en logs recientes, simplemente porque no hay evidencia de que haya llegado un mensaje real de WhatsApp con intención de reserva en la ventana muestreada (~4.5 días). Sigue siendo prioridad máxima de Fase A resolverlo antes de que un cliente real lo dispare.

### 5.4 Rama de auto-deploy de `development`

Confirmado en `railway status --json`: el entorno `development` tiene auto-deploy conectado a la rama `development` del repo `camiloo2525/backEstructuraAI` — igual patrón que `production` con `main`. No hay un tercer entorno ni staging adicional.

### 5.5 Impacto sobre el resto del plan

- **Fase C queda resuelta** con esta sección; ya no bloquea nada.
- La recomendación original de Fase C ("no crear un segundo entorno de staging, mantenerlo simple") debe revisarse: **ya existe** un entorno `development` funcionando, apuntando a una rama (`development`) que la auditoría de la sección 2 ya identificó como desactualizada/redundante frente a `fix/celeste-prompt-and-c07`. Vale la pena decidir, como parte de la Fase B, si `development` (el entorno Railway) se re-apunta a lo que sobreviva de la consolidación de ramas, o se elimina junto con la rama — **esto es una decisión, no se ejecuta sin aprobación explícita**.
- Las Fases A (hotfix) y B (consolidar ramas) siguen sin depender de Railway — se ejecutan sobre git/GitHub. Esta sección solo confirma lo que faltaba de la Fase C.

---

*Documento generado a partir de la sesión de auditoría del 2026-07-06. Complementa, no reemplaza, a `spec/00-entorno-dev.md` — una vez resueltos los puntos de la Fase C, trasladar el estado confirmado a ese documento vivo.*
