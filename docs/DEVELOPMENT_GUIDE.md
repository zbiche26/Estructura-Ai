# Guía de desarrollo

Cómo agregar features, entender las convenciones y trabajar con el proyecto día a día.

---

## Setup inicial

```bash
# 1. Clonar e instalar
pip install -r requirements.txt

# 2. Configurar entorno
cp .env.example .env
# Completar SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET
# Para desarrollo: LLM_PROVIDER=mock y QDRANT_MODE=memory (sin infra extra)

# 3. Levantar
uvicorn src.http.app:app --reload   # Linux/Mac
.\run_api.bat                        # Windows
```

**Verificar que funciona:**
```bash
curl http://localhost:8000/api/v1/health
# o con demo-token (APP_ENV=development)
curl -H "Authorization: Bearer demo-token" \
     -H "X-Tenant-Id: tenant_dev" \
     http://localhost:8000/api/v1/me
```

---

## Agregar un nuevo endpoint

### Paso 1 — Schema Pydantic

Crear o editar un archivo en `src/schemas/`:

```python
# src/schemas/mi_recurso.py
from pydantic import BaseModel
from datetime import datetime

class MiRecursoCreate(BaseModel):
    nombre: str
    descripcion: str | None = None

class MiRecursoResponse(BaseModel):
    id: str
    nombre: str
    tenant_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

### Paso 2 — Repository

Si necesita acceso a Supabase, crear `src/repositories/mi_recurso_repository.py`:

```python
from src.core.database import get_supabase_client

class MiRecursoRepository:
    def __init__(self):
        self.client = get_supabase_client()
        self.table = "mi_tabla"

    async def create(self, tenant_id: str, data: dict) -> dict:
        result = (
            self.client.table(self.table)
            .insert({"tenant_id": tenant_id, **data})
            .execute()
        )
        return result.data[0]

    async def list_by_tenant(self, tenant_id: str) -> list[dict]:
        result = (
            self.client.table(self.table)
            .select("*")
            .eq("tenant_id", tenant_id)
            .execute()
        )
        return result.data
```

### Paso 3 — Servicio

Crear `src/services/mi_recurso_service.py`:

```python
from src.core.tenant_context import get_current_tenant_context
from src.repositories.mi_recurso_repository import MiRecursoRepository
from src.schemas.mi_recurso import MiRecursoCreate

class MiRecursoService:
    def __init__(self):
        self.repo = MiRecursoRepository()

    async def crear(self, data: MiRecursoCreate) -> dict:
        ctx = get_current_tenant_context()
        return await self.repo.create(ctx.tenant_id, data.model_dump())

    async def listar(self) -> list[dict]:
        ctx = get_current_tenant_context()
        return await self.repo.list_by_tenant(ctx.tenant_id)
```

### Paso 4 — Router

Crear `src/http/routers/mi_recurso.py`:

```python
from fastapi import APIRouter, Depends
from src.http.deps import get_current_user
from src.schemas.mi_recurso import MiRecursoCreate, MiRecursoResponse
from src.services.mi_recurso_service import MiRecursoService

router = APIRouter(prefix="/mi-recurso", tags=["Mi Recurso"])

@router.get("/", response_model=list[MiRecursoResponse])
async def listar(
    user=Depends(get_current_user),
    svc: MiRecursoService = Depends()
):
    return await svc.listar()

@router.post("/", response_model=MiRecursoResponse, status_code=201)
async def crear(
    body: MiRecursoCreate,
    user=Depends(get_current_user),
    svc: MiRecursoService = Depends()
):
    return await svc.crear(body)
```

### Paso 5 — Montar el router en la app

Editar `src/http/app.py`:

```python
from src.http.routers.mi_recurso import router as mi_recurso_router

# Junto con los otros app.include_router(...)
app.include_router(mi_recurso_router, prefix="/api/v1")
```

---

## Agregar un nuevo servicio (solo lógica, sin endpoint)

Si el servicio es auxiliar (ej. enviar emails, calcular métricas) y no necesita endpoint propio:

1. Crear `src/services/mi_servicio.py` con la clase del servicio
2. Importarlo donde se use (otro servicio, un worker, el event bus)
3. Si emite eventos, publicar en el `EventBus` en lugar de llamar directamente al destino

```python
from src.core.event_bus import event_bus

# En el servicio que detecta el evento
await event_bus.publish("stock_bajo", {"product_id": pid, "stock": 2})

# En app.py startup, conectar el handler
from src.services.notificaciones import enviar_alerta_stock
event_bus.subscribe("stock_bajo", enviar_alerta_stock)
```

---

## Agregar un nuevo plugin

Ver [CORE.md — Plugin System](./CORE.md#plugin-system) para la interfaz completa.

1. Crear `src/plugins/mi_plugin/plugin.py` con la clase que extiende `BasePlugin`
2. Implementar `load()`, `enable()`, `disable()`
3. En `enable()` suscribirse a los eventos del event bus que el plugin necesita
4. Registrar en `app.py` startup

---

## Migraciones de base de datos

Las migraciones son archivos SQL numerados en `sql/migrations/`. No hay runner automático — se aplican manualmente en Supabase SQL Editor o via CLI.

**Convención de nombre:**
```
sql/migrations/012_nombre_descriptivo.sql
```

**Estructura de una migración:**

```sql
-- 012_agregar_tabla_mi_recurso.sql

CREATE TABLE IF NOT EXISTS mi_tabla (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    nombre TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE mi_tabla ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tenant_isolation" ON mi_tabla
    USING (tenant_id = auth.jwt() ->> 'tenant_id');

-- Índice para queries frecuentes
CREATE INDEX IF NOT EXISTS idx_mi_tabla_tenant
    ON mi_tabla(tenant_id);
```

---

## Testing

### Correr tests

```bash
python -m pytest tests/ -v                    # todos
python -m pytest tests/test_whatsapp.py -v    # archivo específico
python -m pytest tests/ -v -k "test_crear"    # por nombre
```

### Escribir un test

```python
# tests/test_mi_recurso.py
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_crear_mi_recurso():
    with patch("src.repositories.mi_recurso_repository.get_supabase_client") as mock_client:
        mock_client.return_value.table.return_value.insert.return_value.execute.return_value.data = [
            {"id": "123", "nombre": "Test", "tenant_id": "tenant_dev"}
        ]
        
        from src.services.mi_recurso_service import MiRecursoService
        svc = MiRecursoService()
        result = await svc.crear(MiRecursoCreate(nombre="Test"))
        
        assert result["nombre"] == "Test"
```

### Fixture de contexto de tenant

Para tests que usan `get_current_tenant_context()`:

```python
import pytest
from src.core.tenant_context import TenantContextManager, TenantContext

@pytest.fixture
def tenant_context():
    ctx = TenantContext(
        tenant_id="tenant_test",
        slug="test",
        name="Tenant Test",
        is_active=True
    )
    TenantContextManager.set(ctx)
    yield ctx
    TenantContextManager.clear()
```

---

## Variables de entorno para desarrollo

El modo más rápido para desarrollar sin infraestructura:

```env
APP_ENV=development
DEBUG=true
LLM_PROVIDER=mock          # respuestas simuladas, sin costo
QDRANT_MODE=memory         # vector DB en RAM, sin instalar Qdrant
DEFAULT_TENANT_ID=tenant_dev
SUPABASE_URL=              # sí se necesita Supabase real
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
```

Con `APP_ENV=development` se puede usar `Authorization: Bearer demo-token` en todos los endpoints protegidos.

---

## Estructura de carpetas al agregar código

| Qué agregar | Dónde |
|-------------|-------|
| Nuevo endpoint | `src/http/routers/<dominio>.py` |
| Lógica de negocio | `src/services/<nombre>_service.py` |
| Acceso a Supabase | `src/repositories/<nombre>_repository.py` |
| Schema de API | `src/schemas/<dominio>.py` |
| Modelo de dominio | `src/models/<nombre>.py` |
| Componente de infra | `src/core/<nombre>.py` |
| Plugin opcional | `src/plugins/<nombre>/plugin.py` |
| Adaptador externo | `src/integrations/<servicio>.py` |
| Migración DB | `sql/migrations/<NNN>_descripcion.sql` |

---

## Patrones a seguir

### Nunca en un router
- Lógica de negocio (moverla al servicio)
- Llamadas directas a Supabase (pasar por repository)
- Acceso directo al contextvars (usar `Depends(get_tenant_context)`)

### Nunca en un service
- Importar objetos de FastAPI (`Request`, `Response`, `HTTPException` sí está bien)
- Conocer el formato de serialización de la respuesta (eso es del schema)

### Nunca en un repository
- Lógica de negocio (solo CRUD puro)
- Leer el TenantContext (recibir `tenant_id` como parámetro)

### Logging
```python
# Bien: incluir contexto
logger.info("Producto creado", product_id=pid, tenant_id=tid)

# Evitar: logs sin contexto
logger.info("ok")
```

### Errores al cliente
```python
# Para errores esperados (404, 400, 403)
raise HTTPException(status_code=404, detail="Recurso no encontrado")

# Para errores inesperados: loguear + dejar que FastAPI devuelva 500
logger.error("Error inesperado", error=str(e), traceback=True)
raise  # re-raise para no silenciar
```

---

## Flujo de trabajo Git

El proyecto usa ramas de feature con PRs a `main`:

```bash
git checkout -b Feature/nombre-descriptivo
# desarrollar, commits frecuentes
git push origin Feature/nombre-descriptivo
# abrir PR → revisar → merge
```

Los commits siguen el estilo descriptivo en español o inglés (sin convención estricta de Conventional Commits).
