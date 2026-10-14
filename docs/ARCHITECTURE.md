# Arquitectura del sistema — EstructuraAI Backend

## Visión general

EstructuraAI Backend es un servidor FastAPI multi-tenant que expone una API REST para gestionar agentes de ventas IA sobre WhatsApp. La aplicación combina tres bases de datos (relacional, vectorial y caché), un bus de eventos asíncrono, un sistema de plugins y un pipeline de IA con RAG.

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENTES                             │
│  Frontend SPA   ·   WhatsApp Business API   ·   Webhooks    │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP / HTTPS
┌───────────────────────────▼─────────────────────────────────┐
│                    FastAPI (ASGI / Uvicorn)                  │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Middleware chain                         │   │
│  │   TenantContextMiddleware → CORSMiddleware            │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    Routers (18)                       │   │
│  │  health · auth · me · tenants · onboarding · billing │   │
│  │  analytics · conversations · inventory · reports      │   │
│  │  performance · webhooks · notifications · team        │   │
│  │  excel-import · whatsapp-webhook                      │   │
│  └──────────────────────────────────────────────────────┘   │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                     Capa de servicios                        │
│  AgentOrchestrator · AnalyticsService · BillingService      │
│  ConversationManager · InventoryService · ReportService     │
│  NotificationService · MessageWorker · LLMService · …       │
└──────────┬──────────────────────┬───────────────────────────┘
           │                      │
┌──────────▼──────┐   ┌───────────▼──────────────────────────┐
│  Repositories   │   │           Core / Infraestructura       │
│  (Supabase CRUD)│   │  TenantContext · EventBus · PluginSys  │
└──────────┬──────┘   │  Database · Logger · Config            │
           │          └───────────┬──────────────────────────┘
┌──────────▼──────────────────────▼──────────────────────────┐
│                        Persistencia                          │
│  Supabase (PostgreSQL)  ·  Qdrant (vectores)  ·  Redis      │
└─────────────────────────────────────────────────────────────┘
```

---

## Capas de la aplicación

### `src/http/` — Capa HTTP
Contiene todo lo relacionado con la interfaz web:

| Archivo / directorio | Responsabilidad |
|----------------------|-----------------|
| `app.py` | Crea la app FastAPI, registra middleware, monta routers, arranca el worker de mensajes y conecta el event bus al envío de WhatsApp |
| `deps.py` | Dependencias inyectables: `get_current_user()`, `get_tenant_context()`, validación de acceso |
| `routers/` | Un archivo por dominio. Cada router solo orquesta: valida input, llama un servicio y devuelve el schema de respuesta |
| `middleware/` | `TenantContextMiddleware` extrae tenant del header `X-Tenant-Id` o del slug en la URL |

**Convención:** Los routers no contienen lógica de negocio. Si una función hace más que llamar a un servicio, pertenece a `src/services/`.

### `src/services/` — Lógica de negocio (~27 servicios)
Cada servicio es responsable de un dominio:

| Grupo | Servicios |
|-------|-----------|
| Pipeline IA | `agent_orchestrator`, `intent_classifier`, `rag_system`, `knowledge_base`, `response_generator`, `context_manager` |
| WhatsApp | `whatsapp_service`, `message_worker` |
| Datos | `product_search_service`, `vector_service`, `embedding_service`, `cache_service` |
| Negocio | `conversation_manager`, `analytics_service`, `billing_service`, `performance_service`, `report_service`, `notification_service`, `usage_tracker` |
| Inventario | `stock_manager`, `stock_alerts`, `inventory_reports` |
| Auth / Tenant | `auth`, `tenant_service`, `llm_service`, `email_service` |

### `src/repositories/` — Acceso a datos
Encapsulan todas las operaciones CRUD contra Supabase. Los servicios nunca llaman directamente al cliente Supabase; siempre usan un repository.

> Nota: existen `conversation_repo.py` y `conversation_repository.py`. Usar siempre `conversation_repository.py` para código nuevo.

### `src/schemas/` — Contratos de datos
Schemas Pydantic v2 para requests y responses. Separados de los routers para poder reutilizarlos en tests y en otros servicios. Nunca se definen schemas dentro de `src/http/`.

### `src/models/` — Modelos de dominio
Estructuras de datos internas (dataclasses o Pydantic) que representan entidades como `Conversation`, `StockItem`, `Message`. No son schemas de API ni modelos de base de datos.

### `src/core/` — Infraestructura transversal
Componentes que cualquier capa puede usar sin depender de otra capa. Ver [CORE.md](./CORE.md) para detalle.

### `src/integrations/` — Puentes externos
`whatsapp_agent_bridge.py` conecta los mensajes entrantes de WhatsApp con el pipeline del agente. Actúa como adaptador entre el formato de la API de Meta y los modelos internos.

### `src/plugins/` — Sistema de plugins
Funcionalidades opcionales con ciclo de vida propio. Actualmente: `excel_import`, `inventory`. Ver sección Plugin System en [CORE.md](./CORE.md).

### `src/webhooks/` — Eventos externos salientes
Dispatcher que distribuye eventos del sistema a webhooks externos registrados por los tenants.

---

## Ciclo de vida de una request HTTP

```
1. Uvicorn recibe la conexión TCP

2. TenantContextMiddleware
   ├── Lee header X-Tenant-Id  (o slug en la URL para /webhook/whatsapp/{slug})
   ├── Carga TenantContext desde Supabase (con caché Redis)
   └── Inyecta en contextvars — disponible en toda la request

3. CORSMiddleware
   └── Valida origen contra FRONTEND_ORIGINS

4. Router FastAPI
   └── Resolución de dependencias (get_current_user, get_tenant_context)
       └── get_current_user() verifica JWT contra JWKS de Supabase

5. Handler del router
   └── Llama al servicio correspondiente

6. Servicio
   ├── Accede a TenantContext vía get_current_tenant_context()
   ├── Llama a repositories para datos
   └── Devuelve resultado al router

7. Router serializa con schema Pydantic y devuelve JSON

8. Middleware limpia el contextvars (finally block)
```

---

## Ciclo de vida de un mensaje WhatsApp

```
POST /webhook/whatsapp/{tenant_slug}
        │
        ▼
1. Validar firma HMAC-SHA256 del payload
2. ACK inmediato a Meta (< 500 ms) — evita reintentos
3. Persistir job en tabla message_jobs (con UNIQUE en whatsapp_message_id)
        │
        │  (request termina aquí)
        │
        ▼  (background)
4. MessageWorker (poll cada 2s) detecta job pendiente
5. AgentOrchestrator.process_message()
   ├── IntentClassifier  → clasifica la intención
   ├── ContextManager    → actualiza etapa de conversación
   ├── RAGSystem         → busca productos en Qdrant
   └── ResponseGenerator → genera respuesta como "Alex"
6. EventBus emite evento reply_ready
7. Suscriptor envía respuesta vía WhatsApp Business API
8. Job marcado como completed (o failed con retry)
```

---

## Bases de datos

### Supabase (PostgreSQL)
Base de datos principal. Cliente singleton en `src/core/database.py`.

**Tablas clave:**

| Tabla | Propósito |
|-------|-----------|
| `tenants` | Cuentas multi-tenant con configuración WhatsApp |
| `conversations` | Historial de chats por tenant |
| `messages` | Mensajes individuales |
| `products` | Catálogo de productos (metadatos; vectores en Qdrant) |
| `users` | Usuarios de cada tenant |
| `subscription_plans` | Definición de planes Free/Pro/Enterprise |
| `tenant_subscriptions` | Subscripciones activas + estado trial |
| `usage_records` | Tracking diario de uso (mensajes, storage, API calls) |
| `invoices` | Facturas de billing |
| `onboarding_status` | Progreso del wizard por tenant |
| `notifications` | Cola de notificaciones del sistema |
| `message_jobs` | Cola de procesamiento async (UNIQUE en whatsapp_message_id) |
| `error_logs` | Registro de errores del agente |
| `stock_movements` / `stock_reservations` / `stock_alerts` | Gestión de inventario |

**Seguridad:** Row-Level Security (RLS) activo en producción. Los usuarios solo ven datos de su propio tenant.

**Operaciones backend:** Siempre usar `service_role_key` para bypasear RLS desde el servidor.

### Qdrant (Vector DB)
Almacena embeddings de productos para búsqueda semántica. Cada tenant tiene su propia colección: `products_{tenant_id}`.

Modos disponibles via `QDRANT_MODE`:
- `memory` — efímero, solo para desarrollo
- `local` — persistente en disco local
- `cloud` — Qdrant Cloud (producción)

Embeddings generados con OpenAI `text-embedding-3-small`.

### Redis
Caché LRU gestionado por `src/services/cache_service.py`. Usado principalmente para:
- Contexto de tenant (evita round-trips a Supabase por cada request)
- Resultados de búsqueda de productos frecuentes
- Sesiones temporales

---

## Pipeline del agente IA

Ver [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md) para detalle completo.

**Resumen del flujo:**

```
IntentClassifier
  └── 9 tipos: greeting · product_search · price_inquiry · availability
               complaint · farewell · general_inquiry · order_status · support

ContextManager
  └── Etapas: awareness → consideration → decision → purchase
  └── Rastrea: productos mencionados, preferencias, historial

RAGSystem
  └── Embedding del query → búsqueda en Qdrant → recupera top-K productos
  └── Combina resultados vectoriales con filtros SQL (precio, stock)

ResponseGenerator
  └── Persona fija: "Alex"
  └── Tono adaptado a la etapa de conversación
  └── Formato WhatsApp (negrita con *, listas con -)
```

---

## Event Bus

El `EventBus` (`src/core/event_bus.py`) implementa el patrón Observer para comunicación desacoplada entre componentes.

```python
# Suscribirse a un evento
event_bus.subscribe("reply_ready", async_handler)

# Emitir un evento
await event_bus.publish("reply_ready", payload)
```

En `app.py` se conecta el evento `reply_ready` con el envío de WhatsApp durante el startup:

```python
@app.on_event("startup")
async def startup():
    event_bus.subscribe("reply_ready", whatsapp_service.send_message)
```

Soporta handlers síncronos y asíncronos. Si un handler falla, el error se loguea pero no interrumpe a los demás suscriptores.

---

## Sistema de plugins

Patrón micro-kernel. Cada plugin tiene un ciclo de vida:

```
REGISTERED → LOADED → ENABLED → DISABLED
```

Los plugins se comunican con el núcleo vía EventBus, no llamando directamente a servicios. Esto garantiza que activar/desactivar un plugin no rompe el resto del sistema.

Plugins activos:
- `excel_import` — importación masiva de productos desde Excel/CSV
- `inventory` — gestión de stock con alertas automáticas

---

## Autenticación

`src/http/deps.py` provee `get_current_user()`:

1. Extrae el token JWT del header `Authorization: Bearer <token>`
2. Obtiene las claves públicas desde `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
3. Verifica la firma (ES256, RS256, HS256 soportados)
4. Devuelve el payload del usuario

**Modo desarrollo:** Si `APP_ENV=development`, acepta el token `demo-token` sin verificación real. Nunca habilitado en producción.

---

## Configuración

`src/config.py` usa una clase `Settings` (Pydantic BaseSettings) que carga variables desde `.env` y las valida al arrancar. Si faltan variables críticas, la aplicación no arranca.

```python
from src.config import settings

settings.SUPABASE_URL       # acceso tipado
settings.LLM_PROVIDER       # "mock" | "openai" | "anthropic"
```

Ver lista completa de variables en el [README](../README.md#variables-de-entorno).

---

## Logging

Configurado en `src/core/logger.py` con Loguru. Los logs incluyen contexto de tenant cuando está disponible.

```python
from loguru import logger

logger.info("Mensaje procesado", tenant_id=tenant_id, message_id=msg_id)
```

Nivel configurable via `LOG_LEVEL`. En producción se recomienda `INFO`; `DEBUG` solo en desarrollo ya que loguea payloads completos.

---

## Worker de mensajes

`src/services/message_worker.py` es un loop asíncrono que arranca junto con la app:

```
loop: cada 2 segundos
  └── SELECT * FROM message_jobs WHERE status = 'pending' LIMIT 10
      └── por cada job:
          ├── AgentOrchestrator.process_message()
          ├── UPDATE status = 'completed'
          └── en error: UPDATE status = 'failed', retries += 1
                        (máximo 3 reintentos)
```

El constraint UNIQUE en `whatsapp_message_id` previene procesamiento duplicado si Meta reenvía el mismo webhook.

---

## Multi-tenancy

Ver [CORE.md](./CORE.md#multi-tenancy) para implementación detallada.

**Resumen:** Cada tenant es completamente aislado a nivel de datos (RLS en PostgreSQL, colección propia en Qdrant) y de contexto de ejecución (contextvars por request). No hay datos compartidos entre tenants salvo los planes de subscripción.
