# Core — Infraestructura interna

Este documento explica los componentes de `src/core/`: las piezas que toda la aplicación usa y que no dependen de ninguna capa de negocio.

---

## Multi-tenancy

### El problema que resuelve

Múltiples clientes (tenants) comparten el mismo proceso. Cada request debe saber a qué tenant pertenece sin que esa información se pase explícitamente por cada función.

### Implementación: `contextvars`

`src/core/tenant_context.py` usa `contextvars.ContextVar` de Python. A diferencia de una variable global, una `ContextVar` tiene un valor distinto por cada coroutine/tarea en ejecución. Esto es thread-safe y coroutine-safe.

```python
_tenant_context: ContextVar[Optional[TenantContext]] = ContextVar(
    "tenant_context", default=None
)
```

### Flujo completo

```
Request entrante
      │
      ▼
TenantContextMiddleware (src/http/middleware/)
  ├── Lee header X-Tenant-Id
  │   o extrae slug de /webhook/whatsapp/{slug}
  ├── Llama a TenantService.get_tenant_context(tenant_id)
  │   └── Busca en caché Redis → si no → consulta Supabase
  ├── TenantContextManager.set(context)   ← inyecta en contextvars
  └── try:
          yield  ← request se procesa aquí
      finally:
          TenantContextManager.clear()    ← limpieza obligatoria
```

### Leer el contexto desde cualquier parte

```python
from src.core.tenant_context import get_current_tenant_context

def mi_servicio():
    ctx = get_current_tenant_context()
    tenant_id = ctx.tenant_id
    plan = ctx.plan           # feature flags, límites del plan
    config = ctx.config       # configuración del tenant
```

### Lo que contiene `TenantContext`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `tenant_id` | str | ID único del tenant |
| `slug` | str | Identificador amigable para URLs |
| `name` | str | Nombre del negocio |
| `plan` | PlanConfig | Límites: max_products, max_messages, features |
| `config` | TenantConfig | WhatsApp token, configuración del agente |
| `is_active` | bool | Si el tenant puede operar |

### Decorator para proteger funciones

```python
from src.core.tenant_context import require_tenant_context

@require_tenant_context
async def solo_con_tenant():
    # lanza TenantContextError si no hay contexto
    ...
```

---

## Event Bus

### El problema que resuelve

El servicio de agente no debe saber que existe WhatsApp. El procesador de mensajes no debe importar el módulo de WhatsApp. El `EventBus` desacopla quién produce eventos de quién los consume.

### Implementación: Observer pattern

`src/core/event_bus.py` mantiene un diccionario de handlers por nombre de evento.

```python
from src.core.event_bus import event_bus

# Registrar un handler (al arrancar la app)
event_bus.subscribe("reply_ready", send_whatsapp_message)

# Emitir un evento (desde el agente)
await event_bus.publish("reply_ready", {
    "tenant_id": "abc",
    "phone": "+5491155551234",
    "message": "Hola, el producto cuesta $500"
})
```

### Eventos del sistema

| Evento | Quién publica | Quién escucha |
|--------|---------------|---------------|
| `reply_ready` | `AgentOrchestrator` | `WhatsAppService` |
| `message_received` | `WhatsApp webhook` | `MessageWorker` |
| `stock_alert` | `StockManager` | `NotificationService` |
| `job_failed` | `MessageWorker` | `ErrorLogger` |

### Comportamiento ante errores

Si un handler lanza una excepción, el error se loguea con Loguru pero **no interrumpe** a los demás handlers del mismo evento. Cada handler falla de forma independiente.

### Handlers síncronos y asíncronos

El event bus detecta automáticamente si el handler es `async def` o `def` y lo ejecuta en consecuencia. No es necesario uniformizarlos.

```python
# Ambos válidos
event_bus.subscribe("mi_evento", handler_sync)
event_bus.subscribe("mi_evento", handler_async)
```

---

## Plugin System

### El problema que resuelve

Algunas funcionalidades son opcionales o pueden reemplazarse sin modificar el núcleo. El sistema de plugins permite activar/desactivar features en runtime y agregarlas sin tocar el código base.

### Ciclo de vida de un plugin

```
REGISTERED  →  LOADED  →  ENABLED
                              ↓
                          DISABLED
```

| Estado | Qué significa |
|--------|---------------|
| `REGISTERED` | El plugin es conocido por el sistema pero no inicializado |
| `LOADED` | Se ejecutó `plugin.load()`, dependencias verificadas |
| `ENABLED` | Activo y procesando eventos |
| `DISABLED` | Pausado, no procesa eventos pero mantiene estado |

### Crear un plugin

```python
from src.core.plugin_system import BasePlugin, PluginMetadata

class MiPlugin(BasePlugin):
    metadata = PluginMetadata(
        name="mi_plugin",
        version="1.0.0",
        description="Lo que hace",
        dependencies=[]  # nombres de otros plugins requeridos
    )

    async def load(self):
        # inicialización (conexiones, configuración)
        ...

    async def enable(self):
        # registrar handlers en el event bus
        self.event_bus.subscribe("algún_evento", self.handle)
        ...

    async def disable(self):
        # desregistrar handlers, cleanup
        ...

    async def handle(self, payload):
        ...
```

### Registrar un plugin

En `app.py` durante el startup:

```python
plugin_system.register(MiPlugin())
await plugin_system.load("mi_plugin")
await plugin_system.enable("mi_plugin")
```

### Plugins actuales

| Plugin | Función |
|--------|---------|
| `excel_import` | Importa productos desde Excel/CSV con validación y mapeo de columnas. Máx 10 MB, procesamiento async. |
| `inventory` | Gestión de stock: movimientos, reservas, alertas automáticas cuando el stock baja del umbral. |

---

## Database (Supabase)

### Singleton

`src/core/database.py` expone un cliente Supabase único para toda la aplicación:

```python
from src.core.database import get_supabase_client

client = get_supabase_client()
result = client.table("products").select("*").eq("tenant_id", tid).execute()
```

El cliente se crea una sola vez al importar el módulo. No hay pool de conexiones explícito porque el SDK de Supabase maneja la conexión HTTP internamente.

### Service Role vs Anon Key

| Clave | Cuándo usar |
|-------|-------------|
| `SUPABASE_SERVICE_ROLE_KEY` | Siempre en el backend — bypasea RLS |
| `SUPABASE_ANON_KEY` | Solo para operaciones públicas o cuando se quiere respetar RLS de un usuario final |

**El backend siempre usa `service_role_key`.** El RLS protege cuando el cliente es el browser; desde el servidor se aplica la lógica de aislamiento en el código.

### Health check

```python
from src.core.database import check_database_health

is_ok = await check_database_health()
```

Usado por el endpoint `GET /api/v1/health`.

---

## Logger

`src/core/logger.py` configura Loguru con formato estructurado.

### Uso

```python
from loguru import logger

logger.debug("Detalle de debug")
logger.info("Operación completada", tenant_id=tid)
logger.warning("Límite cerca", usage=950, limit=1000)
logger.error("Falló el envío", error=str(e), message_id=mid)
```

### Niveles por entorno

| Entorno | Nivel recomendado | Por qué |
|---------|-------------------|---------|
| `development` | `DEBUG` | Ver payloads completos |
| `production` | `INFO` | Reducir volumen, los payloads pueden contener PII |

### Archivo de log

Configurado por `LOG_FILE` en `.env` (default: `app.log`). En producción se recomienda redirigir a stdout para que el orchestrador de contenedores (Heroku, Railway, etc.) capture los logs.

---

## Configuration (Settings)

`src/config.py` centraliza toda la configuración:

```python
from src.config import settings

# Acceso tipado con autocompletado
settings.APP_ENV           # "development" | "production"
settings.LLM_PROVIDER      # "mock" | "openai" | "anthropic"
settings.SUPABASE_URL
```

### Validación al arrancar

Si una variable requerida no está definida, Pydantic lanza un `ValidationError` antes de que la app empiece a recibir requests. Esto evita errores silenciosos en runtime.

### Variables opcionales con defaults

```python
LLM_PROVIDER: str = "mock"      # safe default para desarrollo
QDRANT_MODE: str = "memory"     # sin infraestructura adicional
LOG_LEVEL: str = "INFO"
```

### Acceder a tokens por tenant (WhatsApp)

Los tokens de WhatsApp son dinámicos por tenant y se leen directamente del entorno:

```python
import os
token = os.getenv(f"WHATSAPP_TOKEN_{tenant_slug.upper()}")
```

---

## Inyección de dependencias (FastAPI)

`src/http/deps.py` centraliza las dependencias compartidas entre routers:

### `get_current_user()`

```python
from src.http.deps import get_current_user
from fastapi import Depends

@router.get("/mi-ruta")
async def mi_handler(user = Depends(get_current_user)):
    return {"user_id": user.id}
```

Flujo interno:
1. Lee `Authorization: Bearer <token>`
2. Descarga JWKS desde Supabase (con caché de 1 hora)
3. Verifica firma JWT (ES256 / RS256 / HS256)
4. En `APP_ENV=development`: acepta `demo-token` → devuelve usuario mock

### `get_tenant_context()`

```python
async def mi_handler(ctx = Depends(get_tenant_context)):
    # ctx ya está cargado por el middleware
    # esta dependencia solo lo extrae para el handler
    return ctx.tenant_id
```

### `require_plan_feature(feature_name)`

Dependencia de orden superior para proteger endpoints por plan:

```python
@router.post("/analytics/export")
async def export(
    _=Depends(require_plan_feature("analytics_export"))
):
    ...
```

Si el plan del tenant no incluye la feature, devuelve `403 Forbidden`.

---

## Convenciones del código

### Estructura de un servicio

```python
# src/services/mi_servicio.py

class MiServicio:
    def __init__(self, repo: MiRepository, cache: CacheService):
        self.repo = repo
        self.cache = cache

    async def hacer_algo(self, tenant_id: str, datos: MiSchema) -> Resultado:
        ctx = get_current_tenant_context()
        # lógica aquí
        return resultado
```

### Estructura de un router

```python
# src/http/routers/mi_router.py
from fastapi import APIRouter, Depends
from src.http.deps import get_current_user
from src.schemas.mi_schema import MiRequest, MiResponse
from src.services.mi_servicio import MiServicio

router = APIRouter(prefix="/mi-recurso", tags=["Mi Recurso"])

@router.get("/", response_model=list[MiResponse])
async def listar(
    user=Depends(get_current_user),
    servicio: MiServicio = Depends()
):
    return await servicio.listar(user.tenant_id)
```

### Schemas vs Models

| Ubicación | Para qué |
|-----------|---------|
| `src/schemas/` | Pydantic: validación de requests/responses de la API |
| `src/models/` | Estructuras internas del dominio (no van a la API) |

### Repositories

Todos los repositories reciben `tenant_id` como parámetro explícito — nunca lo leen del contexto directamente. Esto facilita el testing y hace el aislamiento explícito.

```python
# Correcto
await product_repo.list_products(tenant_id=ctx.tenant_id)

# Evitar dentro del repository
ctx = get_current_tenant_context()  # acoplamiento oculto
```

### Manejo de errores

- Usar excepciones HTTP de FastAPI para errores que el cliente debe recibir:
  ```python
  from fastapi import HTTPException
  raise HTTPException(status_code=404, detail="Producto no encontrado")
  ```
- Usar `logger.error()` + re-raise para errores inesperados.
- No capturar excepciones para ignorarlas silenciosamente.
