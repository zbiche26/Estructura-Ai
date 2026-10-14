
# WhatsApp Multi-Tenant Integration — 
WhatsApp Integration (Multi-Tenant)
-----------------------------------
- Docs: [docs/WHATSAPP_SETUP.md](docs/WHATSAPP_SETUP.md)
- Endpoints: webhooks en `/webhook/whatsapp/{tenant_slug}` (GET/POST)
- Dev start: `./run_api.bat` 
- Env vars:  (`SUPABASE_URL`, `SUPABASE_KEY`/`SUPABASE_SERVICE_ROLE_KEY`, `WHATSAPP_TOKEN_TENANT_<SLUG>`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_WEBHOOK_SECRET`)

Tests
-----
- Unitarios/mocks: `python -m pytest tests/test_whatsapp.py -v`
- Integración Supabase: `python -m pytest tests/test_supabase_tenant.py -v`
	- Necesita `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` o `SUPABASE_KEY` definidos

---

## Variables de entorno y claves por tenant

- Usa nombres en mayúsculas: `SUPABASE_URL`, `SUPABASE_KEY` o `SUPABASE_SERVICE_ROLE_KEY`.
- Tokens de WhatsApp por tenant: `WHATSAPP_TOKEN_<SLUG_EN_MAYUS_CON__>` (ej: `WHATSAPP_TOKEN_TENANT_ABC_123`).
- Campos en la tabla `tenants`:
	- `whatsapp_phone_number`, `whatsapp_phone_id`, `whatsapp_enabled` (bool).
	- `whatsapp_token_encrypted` (se carga desde la env var anterior).
	- `whatsapp_verify_token` (handshake GET, recomendado separado del secreto).
	- `whatsapp_webhook_secret` (firma HMAC POST; si falta verify_token se usa también para el handshake).

---

## Arquitectura y Componentes Clave

- **Aislamiento Multi-Tenant:**
	- Cada request se asocia a un tenant único mediante el header `X-Tenant-ID` o el slug en la URL (`/webhook/whatsapp/{tenant_slug}`).
	- El middleware carga el contexto del tenant antes de procesar la petición y lo limpia automáticamente al finalizar.
	- El contexto incluye credenciales, configuración y límites del tenant, nunca se comparten datos entre clientes.

- **Validación de Seguridad (HMAC):**
	- Todos los webhooks entrantes de WhatsApp (Meta) requieren validación de firma HMAC-SHA256 usando el secreto configurado por tenant (`whatsapp_webhook_secret`).
	- Si la firma es inválida o falta, la petición es rechazada con 403.
	- El token de verificación para el handshake inicial también es por tenant y puede diferir del `whatsapp_webhook_secret` (se usa `whatsapp_verify_token`).

- **Caché y Performance:**
	- Los contextos de tenant se cachean en memoria (thread-safe) con TTL para minimizar consultas a Supabase.
	- El caché se invalida automáticamente si expira o manualmente desde el servicio.

- **Rutas y Routers:**
	- `/webhook/whatsapp/{tenant_slug}`: Endpoints GET (verificación) y POST (recepción de mensajes/status) multi-tenant.
	- `/api/v1/*`: Resto de la API versionada, también soporta multi-tenant.

- **Pruebas y Mocking:**
	- Los tests mockean SupabaseClient y variables de entorno a nivel global, permitiendo simular cualquier escenario multi-tenant sin acceso real a la base de datos.
	- Se valida la lógica de handshake, recepción de mensajes, status updates, errores de firma y aislamiento de datos.

---

### 1. Router WhatsApp Multi-Tenant (`src/http/routers/whatsapp.py`)
	- Nuevo router con endpoints GET/POST para `/webhook/whatsapp/{tenant_slug}`.
	- Validación estricta de firma HMAC-SHA256 por tenant.
	- Respuestas claras para handshake, errores de firma y tenant no encontrado.
	- Uso de `TenantContextManager` para cargar el contexto antes de procesar.

### 2. Middleware de Contexto Multi-Tenant (`src/http/app.py`, `src/api/main.py`)
	- Middleware global que detecta el tenant por header o URL y carga el contexto usando `load_tenant_context`.
	- Limpieza automática del contexto tras cada request.
	- Rutas públicas permitidas sin contexto, el resto requiere tenant válido.

### 3. Handler de WhatsApp (`src/core/whatsapp_handler.py`)
	- Función `parse_meta_payload` para extraer mensajes reales del payload de Meta.
	- Detección de status updates (`has_status_updates`) para ignorar eventos no relevantes.
	- Respuesta estructurada: incluye `status`, `tenant`, `messages_processed`, y detalles de cada mensaje procesado.
	- Generación de `conversation_id` único por tenant y usuario.
	- Manejo robusto de errores y payloads inválidos.

### 4. Servicio de Tenants (`src/services/tenant_service.py`)
	- Búsqueda de tenants por slug, UUID o número de WhatsApp.
	- Construcción de `TenantContext` inmutable con toda la configuración relevante.
	- Inyección de tokens de WhatsApp desde variables de entorno seguras.
	- Caché thread-safe con TTL y helpers para invalidar o recargar.

### 5. Pruebas Automáticas (`tests/test_whatsapp.py`)
	- Mock global de SupabaseClient y variables de entorno antes de importar la app.
	- Generación real de firmas HMAC para los POST (simula seguridad real).
	- Pruebas de handshake, mensajes, status updates, errores de firma, tenant inexistente y carga de campos WhatsApp en el modelo.
	- Todas las rutas y respuestas validadas para multi-tenant.

---
## Flujo Completo

1. **Handshake de Webhook (GET):**
	 - Meta llama a `/webhook/whatsapp/{tenant_slug}?mode=subscribe&token=...&challenge=...`.
	 - El sistema valida el token de verificación del tenant y responde con el challenge si es correcto.
	 - Si el tenant no existe o el token es incorrecto, responde 403 o 404.

2. **Recepción de Mensaje (POST):**
	 - Meta envía un payload firmado a `/webhook/whatsapp/{tenant_slug}` con header `X-Hub-Signature-256`.
	 - El sistema valida la firma HMAC usando el secreto del tenant.
	 - Si es válida, procesa el mensaje, lo asocia al tenant y responde con resumen estructurado.
	 - Si la firma es inválida, responde 403.

3. **Aislamiento Total:**
	 - Cada request se procesa con la configuración y credenciales del tenant correspondiente.
	 - Nunca se mezclan datos ni tokens entre tenants.

4. **Errores y Seguridad:**
	 - Tenant inexistente: 404.
	 - Firma inválida: 403.
	 - Payload inválido: 422 o respuesta de error.

---

## Ejecución de Pruebas

```bash
python -m pytest tests/test_whatsapp.py -v
python -m pytest test/test_supabase_tenant.py -v
```