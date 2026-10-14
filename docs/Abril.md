🔴 CRÍTICOS — 3/3 resueltos

1. ✅ BaseRepository fail closed
   Todos los métodos de lectura/escritura/borrado ahora usan get_current_or_fail(). Si no hay tenant en contexto, lanza ValueError en lugar de ejecutar la query sin filtro.

2. ✅ verify_tenant_access() implementado
   En deps.py — compara el UUID y slug del JWT contra el header X-Tenant-Id. Si no coinciden, retorna 403. Ya no retorna True por defecto.

3. ✅ Bug string en get_message_usage corregido
   En usage_tracker.py — .eq('tenant_id, tenant_id', tenant_id) corregido a .eq('tenant_id', tenant_id).

---

🟠 MEDIOS — 4/4 resueltos

4. ✅ webhooks.py migrado a get_current_user()
   Todos los endpoints de webhooks ahora usan current_user_dep que llama get_current_user() y popula el TenantContextManager correctamente.

5. ✅ plans.py y billing_service.py unificados
   Eliminado PlanKey (free/pro/enterprise). billing_service.py ahora usa TenantPlanEnum (starter/growth/enterprise) como fuente de verdad. Incluye \_normalize_plan_key() para compatibilidad con valores legacy.

6. ✅ rate_limiter.py duplicado eliminado
   Verificamos cuál estaba en uso (src/core/rate_limiter.py — usado en whatsapp_handler.py). El de src/auth/rate_limiter.py no tenía ningún importador — eliminado.

7. ✅ auth/middleware.py unificado con deps.py
   middleware.py ahora es un wrapper sobre deps.get_current_user (JWT propio). TenantAuth se construye desde CurrentUser para mantener compatibilidad con permissions.py. Una sola fuente de verdad.

---

— RLS completo en Supabase

Aprovechamos para aplicar RLS en las 11 tablas que Supabase reportó como públicas. Ahora las 21 tablas del proyecto tienen rls_enabled = true con políticas por tenant.

l 401 que ves en el inbox es esperado — el frontend necesita estar logueado con un tenant real para tener el access_token.

El flujo correcto es:

1. Hacer POST a /api/v1/tenants/login con email + password
2. Guardar el access_token que devuelve
3. Enviarlo en cada request así:
   - Authorization: Bearer <access_token>
   - X-Tenant-Id: eje-inmobiliario

Credenciales de prueba:

- Email: (pedir a camilo)
- Password: (pedir a camilo)

Si ya lo estás enviando y sigue con 401, dime qué ves en el Network tab cuando haces el login — quiero ver si el token está llegando bien al backend.
