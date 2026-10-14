# 📋 Documentación Completa de Endpoints - EstructuraAI API

## 📖 Información General

- **Base URL**: `/api/v1`
- **Autenticación**: JWT Bearer Token (excepto endpoints públicos)
- **Formato**: JSON
- **Versionado**: v1
- **Documentación Interactiva**: `/docs` (Swagger UI)

---

## 🔐 Autenticación y Tenants

### POST /tenants/register
**Público** - Registro de nuevo tenant

**Request Body:**
```json
{
  "name": "Mi Empresa SAS",
  "email": "admin@miempresa.com",
  "password": "SecurePass123!",
  "slug": "mi-empresa",
  "plan": "starter",
  "whatsapp_phone_number": "+573001234568",
  "whatsapp_phone_id": "123456789012345"
}
```

**Response 201:**
```json
{
  "id": "uuid",
  "name": "Mi Empresa SAS",
  "email": "admin@miempresa.com",
  "slug": "mi-empresa",
  "is_active": true,
  "plan": "starter",
  "max_products": 100,
  "max_conversations": 1000,
  "whatsapp_phone_number": "+573001234568",
  "whatsapp_phone_id": "123456789012345",
  "whatsapp_enabled": false,
  "created_at": "2024-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

**Errores:**
- 409: EMAIL_ALREADY_EXISTS, SLUG_ALREADY_EXISTS, WHATSAPP_PHONE_ALREADY_EXISTS, WHATSAPP_PHONE_ID_ALREADY_EXISTS
- 400: VALIDATION_ERROR

### POST /tenants/login
**Público** - Autenticación de tenant

**Request Body:**
```json
{
  "email": "admin@miempresa.com",
  "password": "SecurePass123!"
}
```

**Response 200:**
```json
{
  "access_token": "jwt_token",
  "token_type": "bearer",
  "expires_in": 3600,
  "tenant": {
    "id": "uuid",
    "name": "Mi Empresa SAS",
    "email": "admin@miempresa.com",
    "slug": "mi-empresa",
    "is_active": true,
    "plan": "starter",
    "max_products": 100,
    "max_conversations": 1000,
    "whatsapp_phone_number": "+573001234568",
    "whatsapp_phone_id": "123456789012345",
    "whatsapp_enabled": false,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z"
  }
}
```

**Errores:**
- 401: INVALID_CREDENTIALS
- 403: TENANT_INACTIVE

### PUT /tenants/{tenant_id}
**Autenticado** - Actualizar tenant

**Request Body:**
```json
{
  "name": "Nuevo Nombre",
  "email": "nuevo@email.com",
  "slug": "nuevo-slug",
  "plan": "growth",
  "whatsapp_phone_number": "+573001234569",
  "whatsapp_phone_id": "123456789012346"
}
```

**Response 200:** Misma estructura que registro

### GET /me
**Autenticado** - Información del usuario actual y tenant

**Response 200:**
```json
{
  "user": {
    "id": "uuid",
    "email": "admin@miempresa.com",
    "name": "Admin"
  },
  "tenant": {
    "id": "uuid",
    "name": "Mi Empresa SAS",
    "slug": "mi-empresa",
    "plan": "starter",
    "limits": {
      "max_agents": 1,
      "max_conversations_month": 1000,
      "max_team_members": 2
    },
    "features": ["basic_analytics"],
    "whatsapp_connected": false
  }
}
```

---

## 🤖 Configuración de Agente IA

### GET /agent/config
**Autenticado** - Obtener configuración del agente

**Response 200:**
```json
{
  "nombre_agente": "Asistente Virtual",
  "system_prompt": "Eres un asistente...",
  "welcome_message": "¡Hola! Soy tu asistente",
  "temperatura": 0.7,
  "idioma": "es"
}
```

### PATCH /agent/config
**Autenticado** - Actualizar configuración del agente

**Request Body:**
```json
{
  "nombre_agente": "Nuevo Nombre",
  "temperatura": 0.8
}
```

**Response 200:** Configuración completa actualizada

---

## 📊 Analytics

### GET /analytics/overview?window_days=7
**Autenticado** - Overview general de analytics

**Query Params:**
- `window_days`: 1, 7, 30 (default: 7)

**Response 200:**
```json
{
  "tenant_id": "uuid",
  "total_conversations": 150,
  "active_users": 45,
  "avg_response_time": 2.3,
  "conversations_per_day": {
    "2024-01-01": 10,
    "2024-01-02": 15
  },
  "window_days": 7,
  "calculated_at": "2024-01-01T12:00:00Z"
}
```

### GET /analytics/conversations/day?window_days=30
**Autenticado** - Conversaciones por día

### GET /analytics/conversations/week?weeks=12
**Autenticado** - Conversaciones por semana

### GET /analytics/conversations/month?months=12
**Autenticado** - Conversaciones por mes

### GET /analytics/intents/distribution?days=30
**Autenticado** - Distribución de intents

### GET /analytics/products/top-consulted?days=30&limit=10
**Autenticado** - Top productos consultados

### GET /analytics/products/top-sold?days=30&limit=10
**Autenticado** - Top productos vendidos

---

## 💰 Planes y Facturación

### GET /plans
**Público** - Catálogo de planes disponibles

**Response 200:**
```json
[
  {
    "id": "starter",
    "name": "Starter",
    "slug": "starter",
    "price_monthly": 290000,
    "limits": {
      "max_agents": 1,
      "max_conversations_month": 1000,
      "max_team_members": 2
    },
    "features": ["1 agente IA"]
  }
]
```

### GET /billing/summary
**Autenticado** - Resumen de facturación

**Response 200:**
```json
{
  "data": {
    "plan_id": "starter",
    "status": "active",
    "products_count": 50,
    "conversations_month_count": 750,
    "limits": {
      "products": 100,
      "conversations_month": 1000
    }
  }
}
```

---

## 💬 Conversaciones

### GET /conversations?page=1&page_size=20
**Autenticado** - Listar conversaciones

**Query Params:**
- `page`: número de página (default: 1)
- `page_size`: elementos por página (1-100, default: 20)

**Response 200:**
```json
{
  "data": [
    {
      "id": "conv_123",
      "phone": "+573001234568",
      "contact_name": "Juan Pérez",
      "contact_type": "cliente",
      "status": "active",
      "bot_active": true,
      "last_message": "Gracias por tu ayuda",
      "last_message_at": "2024-01-01T12:00:00.000Z",
      "unread_count": 2
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20
}
```

### GET /conversations/{conversation_id}/messages
**Autenticado** - Obtener mensajes de conversación

**Response 200:**
```json
{
  "data": [
    {
      "id": "msg_123",
      "content": "Hola, necesito ayuda",
      "sender": "contact",
      "status": "read",
      "sent_at": "2024-01-01T12:00:00.000Z"
    }
  ]
}
```

### POST /conversations/{conversation_id}/messages
**Autenticado** - Enviar mensaje

**Request Body:**
```json
{
  "content": "Mensaje de respuesta"
}
```

### PUT /conversations/{conversation_id}
**Autenticado** - Actualizar conversación

**Request Body:**
```json
{
  "bot_active": false,
  "contact_type": "lead",
  "contact_name": "Nuevo Nombre"
}
```

---

## 🔔 Notificaciones

### GET /notifications
**Autenticado** - Listar notificaciones

**Response 200:**
```json
{
  "data": [
    {
      "id": "notif_123",
      "type": "billing",
      "title": "Límite alcanzado",
      "body": "Has alcanzado el 80% de tu límite mensual",
      "read_at": null,
      "created_at": "2024-01-01T12:00:00Z"
    }
  ],
  "total": 5,
  "unread": 3
}
```

### PATCH /notifications/{id}/read
**Autenticado** - Marcar notificación como leída

**Response 200:** Notificación actualizada

---

## 📈 Performance

### GET /performance/response-time?window_minutes=60
**Autenticado** - Tiempo promedio de respuesta

### GET /performance/uptime
**Autenticado** - Uptime del agente

### GET /performance/errors?limit=50
**Autenticado** - Logs de errores recientes

---

## 📋 Onboarding

### GET /onboarding/status
**Autenticado** - Estado del proceso de onboarding

**Response 200:**
```json
{
  "data": {
    "whatsapp_connected": true,
    "training_done": false,
    "first_conversation_done": true
  }
}
```

---

## 📊 Reportes

### GET /reports/weekly?start_date=2024-01-01&end_date=2024-01-07
**Autenticado** - Reporte semanal

### GET /reports/monthly?year=2024&month=1
**Autenticado** - Reporte mensual

### GET /reports/export?period=weekly&format=csv
**Autenticado** - Exportar reporte

---

## 👥 Equipo

### GET /team/members
**Autenticado** - Miembros del equipo

### POST /team/members
**Autenticado** - Invitar miembro

### DELETE /team/members/{user_id}
**Autenticado** - Remover miembro

---

## 📁 Inventario/Productos

### GET /inventory/products?page=1&page_size=20
**Autenticado** - Listar productos

### POST /inventory/products
**Autenticado** - Crear producto

### PUT /inventory/products/{product_id}
**Autenticado** - Actualizar producto

### DELETE /inventory/products/{product_id}
**Autenticado** - Eliminar producto

### POST /inventory/products/{product_id}/stock
**Autenticado** - Actualizar stock

---

## 📊 Excel Import

### POST /excel/import
**Autenticado** - Importar datos desde Excel

**Request:** Form data con archivo Excel

---

## 🔄 Webhooks

### POST /webhooks/whatsapp
**Público** - Webhook de WhatsApp Business API

### POST /webhooks/{tenant_slug}/{webhook_type}
**Público** - Webhooks personalizados por tenant

---

## 🏥 Health Checks

### GET /health
**Público** - Health check básico

**Response 200:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "version": "0.1.0"
}
```

### GET /health/detailed
**Autenticado** - Health check detallado con métricas

---

## ⚠️ Códigos de Error Comunes

- **400**: VALIDATION_ERROR - Datos inválidos
- **401**: INVALID_CREDENTIALS - Credenciales incorrectas
- **403**: TENANT_INACTIVE - Tenant inactivo
- **404**: NOT_FOUND - Recurso no encontrado
- **409**: CONFLICT - Conflicto (duplicados, etc.)
- **422**: VALIDATION_ERROR - Validación Pydantic
- **500**: INTERNAL_ERROR - Error interno
- **503**: SERVICE_UNAVAILABLE - Servicio no disponible

---

## 🔒 Seguridad

- Todos los endpoints requieren JWT Bearer Token (excepto públicos)
- Multi-tenant: aislamiento por `tenant_id`
- Rate limiting aplicado
- Logs de auditoría en operaciones sensibles
- Validación estricta de entrada/salida
---