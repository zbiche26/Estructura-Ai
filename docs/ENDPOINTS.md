# Documentación de Endpoints — Estructura IA Backend
Prueba de rama
> Base URL: `http://localhost:8000/api/v1`  
> Total de endpoints: **48**  
> Autenticación: `X-Tenant-Id: <uuid>` en el header (o `Authorization: Bearer <token>` según el endpoint)

---

## 1. Analytics — `/analytics`
**Tags:** `Analytics`  
**Auth:** Todos requieren `Authorization: Bearer <token>` + tenant context.

### GET `/analytics/overview`
Resumen general de actividad del tenant.

| Parámetro | Tipo | Dónde | Requerido | Default | Descripción |
|-----------|------|-------|-----------|---------|-------------|
| `window_days` | int [1-90] | query | No | `7` | Días hacia atrás para el análisis |

**Respuesta 200:** `AnalyticsOverviewResponse`

---

### GET `/analytics/conversations/day`
Serie de conversaciones agrupadas por día.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `window_days` | int [1-180] | query | No | `30` |

**Respuesta 200:** `AnalyticsSeriesResponse`

---

### GET `/analytics/conversations/week`
Serie de conversaciones agrupadas por semana.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `weeks` | int [1-52] | query | No | `12` |

**Respuesta 200:** `AnalyticsSeriesResponse`

---

### GET `/analytics/conversations/month`
Serie de conversaciones agrupadas por mes.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `months` | int [1-24] | query | No | `12` |

**Respuesta 200:** `AnalyticsSeriesResponse`

---

### GET `/analytics/intents/distribution`
Distribución de intents detectados por el agente.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `days` | int [1-180] | query | No | `30` |

**Respuesta 200:** `IntentDistributionResponse`

---

### GET `/analytics/products/top-consulted`
Productos más consultados por los usuarios.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `days` | int [1-365] | query | No | `30` |
| `limit` | int [1-50] | query | No | `10` |

**Respuesta 200:** `TopProductsConsultedResponse`

---

### GET `/analytics/products/top-sold`
Productos más vendidos.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `days` | int [1-365] | query | No | `30` |
| `limit` | int [1-50] | query | No | `10` |

**Respuesta 200:** `TopProductsSoldResponse`

---

## 2. Auth — `/auth`
**Tags:** `auth`  
⚠️ Endpoints stub — en desarrollo devuelven datos de demo.

### POST `/auth/login`
Autenticación de usuario (stub).

**Body JSON:**
```json
{ "email": "string", "password": "string" }
```

**Respuesta 200:** `LoginResponse` — devuelve `demo-token` en dev, `disabled` en prod.

---

### GET `/auth/me`
Obtiene el contexto del usuario actual.

**Respuesta 200:** `MeResponse`

---

## 3. Billing — `/billing`
**Tags:** `billing`

### GET `/billing/summary`
Resumen de plan, trial y uso para el paywall (stub).

**Respuesta 200:** `BillingSummaryResponse`

---

## 4. Excel Import — `/plugins/excel`
**Tags:** `Excel Import`

### POST `/plugins/excel/upload`
Sube un archivo Excel/CSV para importar productos. Procesamiento asíncrono.

**Body:** `multipart/form-data`

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `file` | UploadFile | Sí | Archivo `.xlsx`, `.xls` o `.csv`. Máximo 10MB |

**Respuesta 202:**
```json
{ "import_id": "uuid", "status": "processing", "message": "..." }
```

---

### GET `/plugins/excel/template`
Descarga el template de productos en formato Excel.

**Respuesta 200:** Archivo `.xlsx` descargable. No requiere autenticación.

---

### GET `/plugins/excel/imports`
Historial paginado de importaciones del tenant.

| Parámetro | Tipo | Dónde | Requerido | Default | Descripción |
|-----------|------|-------|-----------|---------|-------------|
| `page` | int [ge=1] | query | No | `1` | Página actual |
| `limit` | int [1-100] | query | No | `10` | Resultados por página |
| `status` | string | query | No | — | Filtrar por: `processing`, `completed`, `failed` |

**Respuesta 200:** `ExcelImportListResponse`

---

### GET `/plugins/excel/imports/{import_id}`
Detalle completo de una importación específica.

| Parámetro | Tipo | Dónde | Requerido |
|-----------|------|-------|-----------|
| `import_id` | string | path | Sí |

**Respuesta 200:** `ExcelImportDetailResponse`  
**Respuesta 404:** Import no encontrada.

---

## 5. Health — `/`
**Tags:** `health`

### GET `/health`
Comprueba que el servidor está activo.

**Respuesta 200:**
```json
{ "status": "ok" }
```

---

## 6. Inventory — `/plugins/inventory`
**Tags:** `Inventory`

### GET `/plugins/inventory/stock`
Stock actual de productos del tenant.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `low_stock_only` | bool | query | No | `false` |
| `search` | string | query | No | — | Filtra por nombre o SKU |

**Respuesta 200:** `InventoryStockResponse`

---

### POST `/plugins/inventory/adjust`
Ajuste manual de stock de un producto.

**Body JSON:**
```json
{ "product_id": "uuid", "adjustment": -5 }
```

**Respuesta 202:** `StockAdjustResponse`

---

### GET `/plugins/inventory/alerts`
Alertas de stock bajo, crítico o agotado.

| Parámetro | Tipo | Dónde | Requerido | Valores |
|-----------|------|-------|-----------|---------|
| `level` | enum | query | No | `warning`, `critical`, `urgent` |

**Respuesta 200:** `InventoryAlertsResponse`

---

### GET `/plugins/inventory/history`
Historial paginado de movimientos de inventario.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `page` | int [ge=1] | query | No | `1` |
| `limit` | int [1-50] | query | No | `10` |
| `product_id` | string | query | No | — |

**Respuesta 200:** `StockHistoryResponse`

---

## 7. Me — `/me`
**Tags:** `me`

### GET `/me`
Devuelve el contexto del tenant/usuario autenticado actual.

**Header:** `Authorization: Bearer <token>` (opcional)

**Respuesta 200:** `MeResponse`

---

## 8. Onboarding — `/onboarding`
**Tags:** `onboarding`

### GET `/onboarding/status`
Estado del checklist de onboarding del tenant (stub).

**Respuesta 200:** `OnboardingStatusResponse`

---

## 9. Performance — `/performance`
**Tags:** `Performance`

### GET `/performance/response-time`
Promedio de tiempo de respuesta del agente IA.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `window_minutes` | int [1-720] | query | No | `PERFORMANCE_WINDOW_MINUTES` (env) |

**Respuesta 200:** `AgentResponseTimeResponse`

---

### GET `/performance/uptime`
Uptime del agente IA y fuente de inicio.

**Respuesta 200:** `AgentUptimeResponse`

---

### GET `/performance/error-logs`
Logs de errores recientes del tenant.

| Parámetro | Tipo | Dónde | Requerido | Default |
|-----------|------|-------|-----------|---------|
| `limit` | int [1-100] | query | No | `50` |

**Respuesta 200:** `ErrorLogsResponse`

---

## 10. Reports — `/reports`
**Tags:** `Reports`

### GET `/reports/weekly`
Reporte semanal de ventas.

**Respuesta 200:** `WeeklyReportResponse`

---

### GET `/reports/monthly`
Reporte mensual de ventas.

| Parámetro | Tipo | Dónde | Requerido | Descripción |
|-----------|------|-------|-----------|-------------|
| `year` | int [2000-2100] | query | No | Año del reporte |
| `month` | int [1-12] | query | No | Mes del reporte |

**Respuesta 200:** `MonthlyReportResponse`

---

### GET `/reports/export`
Exporta un reporte en formato JSON con contenido base64.

| Parámetro | Tipo | Dónde | Requerido | Valores |
|-----------|------|-------|-----------|---------|
| `period` | string | query | Sí | `weekly`, `monthly` |
| `format` | string | query | Sí | `csv`, `pdf` |

**Respuesta 200:** `ExportReportResponse`

---

### GET `/reports/export/download`
Descarga directa del archivo de reporte (streaming binario).

| Parámetro | Tipo | Dónde | Requerido | Valores |
|-----------|------|-------|-----------|---------|
| `period` | string | query | Sí | `weekly`, `monthly` |
| `format` | string | query | Sí | `csv`, `pdf` |

**Respuesta 200:** `StreamingResponse` (archivo binario)

---

## 11. Tenants — `/tenants`
**Tags:** `Tenants`, `Management`

### POST `/tenants/register`
Registra un nuevo tenant en el sistema.

**Body JSON:**
```json
{
  "name": "Mi Empresa",
  "email": "admin@empresa.com",
  "password": "Segura123!",
  "slug": "mi-empresa",
  "plan": "starter",
  "whatsapp_phone_number": "+573001112233"
}
```

**Respuesta 201:** `TenantCreatedResponse`  
**Errores:** 409 si email, slug o WhatsApp ya existe.

---

### POST `/tenants/login`
Autentica un tenant y devuelve tokens JWT.

**Body JSON:**
```json
{ "email": "admin@empresa.com", "password": "Segura123!" }
```

**Respuesta 200:** `TenantLoginResponse`
```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3600,
  "tenant": { ... }
}
```
**Errores:** 401 credenciales inválidas. Bloqueo tras 5 intentos fallidos.

---

### POST `/tenants/refresh-token`
Rota access y refresh tokens.

**Body JSON:**
```json
{ "refresh_token": "..." }
```

**Respuesta 200:** `TenantLoginResponse` (nuevos tokens)  
**Rate limit:** 30 solicitudes/min.

---

### POST `/tenants/logout`
Invalida la sesión del tenant.

**Headers:** `Authorization: Bearer <access_token>`  
**Body JSON:**
```json
{ "refresh_token": "..." }
```

**Respuesta 200:**
```json
{ "detail": "Logout exitoso" }
```

---

### POST `/tenants/forgot-password`
Solicita recuperación de contraseña.

**Body JSON:**
```json
{ "email": "admin@empresa.com" }
```

**Respuesta 200:** `ForgotPasswordResponse`  
⚠️ Respuesta genérica (anti-enumeración de usuarios).

---

### POST `/tenants/reset-password`
Cambia la contraseña con un token de recuperación.

**Body JSON:**
```json
{ "token": "...", "new_password": "NuevaSegura123!" }
```

**Respuesta 200:** `MessageResponse`

---

### PUT `/tenants/{tenant_id}`
Actualiza los datos del tenant.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `tenant_id` | string | path |

**Body JSON (todos opcionales):**
```json
{
  "name": "Nuevo Nombre",
  "email": "nuevo@email.com",
  "slug": "nuevo-slug",
  "plan": "pro",
  "whatsapp_phone_number": "+573009998877"
}
```

**Respuesta 200:** `TenantResponse`

---

### POST `/tenants/{tenant_id}/api-keys`
Genera una nueva API key para el tenant.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `tenant_id` | string | path |

**Body JSON (opcional):**
```json
{ "name": "Mi API Key" }
```

**Respuesta 201:** `ApiKeyResponse`
```json
{
  "id": "uuid",
  "api_key": "raw-key-solo-visible-aqui",
  "name": "Mi API Key",
  "created_at": "2026-03-27T..."
}
```
⚠️ El valor de `api_key` solo se muestra una vez en la creación.

---

### DELETE `/tenants/{tenant_id}/api-keys/{key_id}`
Revoca una API key existente.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `tenant_id` | string | path |
| `key_id` | string | path |

**Respuesta 200:** `MessageResponse`

---

### GET `/tenants/{tenant_id}/usage`
Uso de mensajes y almacenamiento del período actual.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `tenant_id` | string | path |

**Respuesta 200:** `UsageResponse`

---

### GET `/tenants/{tenant_id}/billing`
Información básica de facturación del tenant.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `tenant_id` | string | path |

**Respuesta 200:** `BillingInfoResponse`
```json
{ "plan": "starter", "status": "active", "billing_cycle": "monthly", "next_billing_date": "..." }
```

---

## 12. Webhooks — `/webhooks`
**Tags:** `webhooks`  
**Auth:** Header `X-Tenant-Id: <uuid>` requerido en todos los endpoints.

### POST `/webhooks/`
Crea un webhook para el tenant. El `secret` es generado automáticamente por el backend.

**Body JSON:**
```json
{
  "name": "Webhook Productos",
  "url": "https://tuservidor.com/webhook",
  "description": "Notifica cuando se crea un producto",
  "events": ["product.created", "product.updated"],
  "headers": { "X-Custom-Header": "valor" },
  "is_active": true
}
```

**Respuesta 201:** `WebhookResponse`
```json
{
  "id": "uuid",
  "tenant_id": "uuid",
  "name": "Webhook Productos",
  "url": "https://tuservidor.com/webhook",
  "secret": "whsec_a1b2c3...",
  "events": ["product.created"],
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

---

### GET `/webhooks/`
Lista todos los webhooks del tenant con paginación.

| Parámetro | Tipo | Dónde | Default |
|-----------|------|-------|---------|
| `limit` | int [1-200] | query | `50` |
| `offset` | int [ge=0] | query | `0` |

**Respuesta 200:** `WebhookListResponse`
```json
{ "items": [...], "total": 5 }
```

---

### GET `/webhooks/{webhook_id}`
Obtiene el detalle de un webhook específico.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `webhook_id` | UUID | path |

**Respuesta 200:** `WebhookResponse`  
**Respuesta 404:** Webhook no encontrado.

---

### PUT `/webhooks/{webhook_id}`
Actualiza parcialmente un webhook (solo los campos enviados).

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `webhook_id` | UUID | path |

**Body JSON (todos opcionales):**
```json
{
  "name": "Nuevo nombre",
  "url": "https://nuevo-endpoint.com/hook",
  "is_active": false,
  "events": ["sale.completed"]
}
```

**Respuesta 200:** `WebhookResponse`  
**Respuesta 404:** Webhook no encontrado.

---

### DELETE `/webhooks/{webhook_id}`
Elimina un webhook permanentemente.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `webhook_id` | UUID | path |

**Respuesta 204:** Sin contenido.  
**Respuesta 404:** Webhook no encontrado.

---

### GET `/webhooks/{webhook_id}/deliveries`
Historial de entregas de un webhook (auditoría de envíos).

| Parámetro | Tipo | Dónde | Default |
|-----------|------|-------|---------|
| `webhook_id` | UUID | path | — |
| `limit` | int [1-200] | query | `50` |
| `offset` | int [ge=0] | query | `0` |

**Respuesta 200:** `list[WebhookDeliveryResponse]`
```json
[
  {
    "id": "uuid",
    "webhook_id": "uuid",
    "tenant_id": "uuid",
    "delivery_status": "success",
    "response_status_code": 200,
    "response_body": "...",
    "error_message": null,
    "request_payload": { ... },
    "event_type": "product.created",
    "attempt": 1,
    "created_at": "..."
  }
]
```

---

### POST `/webhooks/{webhook_id}/test`
Dispara un envío de prueba al endpoint del webhook y registra la entrega.

| Parámetro | Tipo | Dónde |
|-----------|------|-------|
| `webhook_id` | UUID | path |

**Body JSON:**
```json
{
  "payload": {
    "event": "product.created",
    "data": { "id": "prod_123", "name": "Zapatos", "price": 49.99 }
  },
  "headers": { "X-Debug": "true" }
}
```

**Respuesta 200:** `WebhookDeliveryResponse` (delivery registrado)  
**Respuesta 404:** Webhook no encontrado.  
**Respuesta 502:** El endpoint remoto devolvió error o no fue alcanzable.

> 💡 **Nota:** Si el campo `event` no está presente en el payload, se guarda `event_type = "test"` automáticamente.

---

## 13. WhatsApp — `/webhook/whatsapp`
**Tags:** `whatsapp`

### GET `/webhook/whatsapp/{tenant_id}`
Verificación del webhook de WhatsApp Cloud API (handshake de Meta).

| Parámetro | Tipo | Dónde | Descripción |
|-----------|------|-------|-------------|
| `tenant_id` | string | path | UUID o slug del tenant |
| `hub.mode` | string | query | Debe ser `subscribe` |
| `hub.verify_token` | string | query | Token de verificación configurado en el tenant |
| `hub.challenge` | string | query | Challenge de Meta para que el servidor devuelva |

**Respuesta 200:** Devuelve el `challenge` si la verificación es exitosa.  
**Respuesta 403:** `"Verification failed"` si el token no coincide.

---

### POST `/webhook/whatsapp/{tenant_id}`
Recibe mensajes y eventos de WhatsApp. Validación HMAC-SHA256 obligatoria.

| Parámetro | Tipo | Dónde | Descripción |
|-----------|------|-------|-------------|
| `tenant_id` | string | path | UUID o slug del tenant |
| `X-Hub-Signature-256` | string | header | Firma HMAC-SHA256 del payload con el `whatsapp_webhook_secret` del tenant |

**Body JSON:** Payload estándar de WhatsApp Cloud API (mensajes, status, etc.)

**Respuesta 200:** Resultado del handler del agente.  
**Respuesta 403:** Firma inválida.  