← [Índice](./README.md)

# Fase 0 — Cuadrar el entorno de desarrollo (antes de seguir)

Esto es lo primero que hay que cerrar. Sin esto definido, cada deploy sigue siendo un riesgo manual.

## 0.1 — Estado confirmado en Railway

**Actualizado 2026-07-06** con acceso real al proyecto y verificación en modo solo lectura (detalle completo en `spec/00-auditoria-y-plan-2026-07.md` sección 5):

- Proyecto Railway: `refreshing-respect` (workspace de `camiloo2525`), servicio `backEstructuraAI`.
- Entorno `production`: rama `main` conectada con auto-deploy activado en cada push. Dominio: `backestructuraai-production.up.railway.app`.
- **Sí existe un segundo entorno** — corrige lo que decía antes esta sección: `development`, con auto-deploy conectado a la rama `development` del mismo repo. Dominio: `backestructuraai-development.up.railway.app`. Su último deploy activo (confirmado 2026-07-06) es del 2026-05-28, anterior a los fixes recientes de C07 — no representa el estado actual de ninguna rama candidata sin revisarlo de nuevo.
- No hay `railway.json` ni `railway.toml` en el repo — los dos entornos están configurados directamente en la plataforma Railway, no como IaC versionado.
- No hay un tercer entorno ni un servicio de staging adicional.

## 0.2 — Decisión pendiente: qué hacer con la rama `development` (y su entorno Railway)

La rama `development` diverge de `main`: tiene commits que `main` no tiene y le faltan commits que sí están en `main`. **A diferencia de lo que decía esta sección antes, sí está conectada a un entorno real en Railway** (ver 0.1) — la decisión ya no es solo sobre la rama de git, también sobre qué hacer con ese entorno.

La auditoría de 2026-07-06 (`spec/00-auditoria-y-plan-2026-07.md` sección 2) ya revisó el contenido completo de la rama: los 3 commits de notificaciones que tiene de más ya están en `main` por otra vía; el único valor real no cubierto en `main` es el manejo 503 en `GET /agent/config` (ver 0.3). No hay nada más que rescatar.

- [x] Revisar si `development` tiene algo más de valor además del fix de amnesia/UUID (ver 0.3) — resuelto: solo el 503, nada más.
- [ ] Traer el fix de 503 a `fix/celeste-prompt-and-c07` antes de mergear a `main` (ver 0.3)
- [ ] Decidir, junto con la limpieza de ramas, qué pasa con el entorno Railway `development`: ¿se re-apunta a lo que sobreviva de la consolidación, o se elimina junto con la rama? **No se ejecuta sin aprobación explícita** — es una acción sobre infraestructura compartida.

> **La recomendación original ("eliminar `development`, sin ambiente de staging separado") sigue siendo razonable, pero ya no es un no-op**: hoy existe un entorno Railway corriendo un deploy de hace más de un mes. Dejarlo como está también es una decisión, no un default neutral.

## 0.3 — Fix pendiente: manejo 503 en `GET /agent/config` (amnesia UUID ya resuelta en `main`)

Commit `522b316` en `origin/development` (no está en `main`) corregía dos problemas:

- Traducción de `conversation_id` temporal (formato `wa_xxxxx`) al ID real de la conversación en Supabase, evitando que el agente pierda el hilo de la conversación.
- Manejo de errores en el endpoint de configuración del agente (`GET agent/config`): antes fallaba con 500 crudo si Supabase no respondía; ahora devuelve 503 controlado.

**Confirmado por la auditoría de 2026-07-06** (`spec/00-auditoria-y-plan-2026-07.md` sección 2), leyendo `origin/main` directamente:

- [x] Comparar `522b316` (development) contra `d6be59a` (main) — **resuelto**: la parte de `conversation_id` temporal ya está cubierta en `main` de otra forma, con `_resolve_conversation_id` en `app.py`. No hace falta traer esa parte.
- [ ] Traer únicamente el manejo 503 de `GET /agent/config` (`src/http/routers/agent.py`, ~9 líneas: envolver `agent_config_repo.get_by_tenant_id()` en try/except y devolver 503 en vez de 500 crudo) — esto sigue pendiente, `main` no lo tiene. Incluirlo en el mismo PR de `fix/celeste-prompt-and-c07` → `main`.

## 0.4 — Flujo de trabajo Git definido (ajustado 2026-07-06: trabajo individual, sin PR formal)

Trabajo sola en este proyecto — no hay PRs en GitHub ni revisión de otra persona. La revisión de diff antes del merge la hago yo misma y reemplaza esa función. **Regla dura: nunca rebase de ramas existentes ni reescritura de historial — toda reconciliación con `main` se hace con `merge`.**

1. Ritual de inicio de sesión, sin excepción: `git fetch --all --prune` + `git branch -vv` + `git status` antes de tocar cualquier archivo, para partir de un estado confirmado y detectar ramas desalineadas.
2. Toda rama nueva nace de `main` actualizado: `git checkout main` → `git pull origin main` → `git checkout -b tipo/nombre-descriptivo`.
3. Trabajo y commits normales sobre esa rama.
4. Para traer cambios nuevos de `main` hacia una rama de trabajo ya existente (ej. `fix/celeste-prompt-and-c07`): **merge, nunca rebase** — `git checkout tipo/nombre` → `git merge main`. Trae los cambios sin reescribir el historial de ninguna de las dos ramas.
5. Antes de mergear a `main`: revisar el diff yo misma — primero `git diff --stat main..tipo/nombre` para ver el alcance, luego el diff completo. Nunca interpretar el diff línea a línea como si fuera el contenido final del archivo.
6. Correr los tests relevantes localmente.
7. Merge local directo a `main` (nunca rebase): `git checkout main` → `git merge tipo/nombre` → `git push origin main` → Railway autodespliega.
8. Confirmar en logs de Railway que el deploy arrancó sin errores + prueba real del flujo afectado.
9. Borrar la rama ya mergeada de inmediato, local y remota: `git branch -d tipo/nombre` + `git push origin --delete tipo/nombre`. Nada de ramas flotando sin cerrar.

Se mantienen sin cambios:
- Mini-spec obligatoria antes de tocar archivos de riesgo alto (system prompt, `agent_orchestrator.py`, `app.py`): qué cambia, por qué, qué se rompe si sale mal, cómo se prueba.
- TDD para bugs en archivos compartidos o críticos: test RED que confirme el bug, luego GREEN que confirme el fix.
- Sin worktrees — una sola carpeta de trabajo, cambio de rama estándar con `git checkout`.
- Antes de cualquier push: confirmar con `git branch -vv` que el upstream de la rama local apunta a su propia rama remota, no a `main`.

---
→ Siguiente: [01-produccion-mvp.md](./01-produccion-mvp.md)
