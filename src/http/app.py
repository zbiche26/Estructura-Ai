# src/http/app.py
from __future__ import annotations

import os
from typing import List

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from fastapi import Request
from fastapi.responses import JSONResponse

from .routers.auth_stub import router as auth_router
from .routers.health import router as health_router
from .routers.me import router as me_router
from .routers.whatsapp import router as whatsapp_router
from .routers.tenants import router as tenants_router
from .routers import onboarding
from .routers import billing
from .routers import plans
from .routers import excel
from .routers import inventory
from .routers import webhooks
from .routers import analytics_router
from .routers import performance_router
from .routers import report_router
from .routers import conversations
from .routers import team
from .routers import conversations_import
from .routers import notifications
from .routers import agent

from src.core.tenant_context import TenantContextManager
from src.services.tenant_service import load_tenant_context
from src.core.logger import logger

API_PREFIX = "/api/v1"


OPENAPI_TAGS = [
    {"name": "health", "description": "Health checks"},
    {"name": "auth", "description": "Auth stubs (temporary)"},
    {"name": "me", "description": "Current user + tenant context (canonical)"},
    {"name": "onboarding", "description": "Onboarding status and checklist"},
    {
        "name": "billing",
        "description": "Billing summary, plan status, and usage/limits",
    },
    {"name": "plans", "description": "Plans catalog (for pricing/upgrade UI)"},
    {"name": "whatsapp", "description": "WhatsApp webhook endpoints "},
    {"name": "webhooks", "description": "Tenant webhook management endpoints"},
    {"name": "Excel Import", "description": "Excel import plugin endpoint "},
    {"name": "Inventory", "description": "Inventory plugin endpoints "},
    {
        "name": "Analytics",
        "description": "Analytics endpoints for conversations and products",
    },
    {"name": "Conversations", "description": "Listado y gestión de conversaciones"},
    {"name": "Performance", "description": "Métricas de performance del agente"},
    {"name": "Agent", "description": "Configuración y estado del agente IA"},
    {"name": "Reports", "description": "Reportes semanales/mensuales y exportación"},
    {"name": "Notifications", "description": "Notificaciones del sistema por tenant"},
]

# Rutas que NO requieren contexto de tenant
PUBLIC_PATHS = {
    "/",
    "/favicon.ico",
    "/health",
    "/api/v1/health",
    "/api/v1/docs",
    "/api/v1/redoc",
    "/api/v1/openapi.json",
    "/api/v1/plans",
    "/docs",
    "/redoc",
    "/openapi.json",
}


def parse_origins() -> List[str]:
    raw = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://192.168.1.9:3000",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


def add_cors(app: FastAPI, origins: List[str]) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_api_v1(origins: List[str]) -> FastAPI:
    api_v1 = FastAPI(
        title="EstructuraAI API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
        redirect_slashes=False,
    )

    add_cors(api_v1, origins)

    api_v1.include_router(health_router)
    api_v1.include_router(auth_router)
    api_v1.include_router(tenants_router)
    api_v1.include_router(me_router)
    api_v1.include_router(onboarding.router)
    api_v1.include_router(billing.router)
    api_v1.include_router(plans.router)
    api_v1.include_router(excel.router)
    api_v1.include_router(inventory.router)
    api_v1.include_router(webhooks.router)
    api_v1.include_router(analytics_router.router)
    api_v1.include_router(performance_router.router)
    api_v1.include_router(report_router.router)
    api_v1.include_router(conversations.router)
    api_v1.include_router(team.router)
    api_v1.include_router(conversations_import.router)
    api_v1.include_router(notifications.router)
    api_v1.include_router(agent.router)

    return api_v1


def create_app() -> FastAPI:
    """
    Root app:
      - Startup: suscribe agente al event bus
      - Middleware de contexto tenant (multi-tenant)
      - CORS
      - Mounts versioned API under /api/v1
      - Monta webhooks de WhatsApp en la raíz
    """
    app = FastAPI(
        title="EstructuraAI API",
        version="0.1.0",
        description="HTTP layer (routers + schemas + stubs).",
        openapi_tags=OPENAPI_TAGS,
        redirect_slashes=False,
    )

    origins = parse_origins()
    add_cors(app, origins)

    # ------------------------------------------------------------------
    # STARTUP: Suscribir agente al event bus
    # ------------------------------------------------------------------
    @app.on_event("startup")
    async def startup_event():
        from src.core.event_bus import event_bus
        from src.services.agent_reply_handler import handle_agent_reply

        event_bus.subscribe("agent.reply.requested", handle_agent_reply)
        logger.info("✅ Agente suscrito al event bus — listo para responder WhatsApp")

        # ── Worker loop: procesa cola message_jobs cada 2 segundos ──
        from src.services.message_worker import process_pending_jobs, should_run_worker

        async def worker_loop():
            loop_count = 0
            while True:
                try:
                    await process_pending_jobs()
                except Exception as e:
                    logger.error(f"[WORKER LOOP] Error: {e}")

                # ✅ C07: Liberar reservas expiradas cada 5 minutos
                loop_count += 1
                if loop_count % 150 == 0:  # 150 * 2s = 5 minutos
                    try:
                        from src.services.reservation_service import (
                            release_expired_reservations,
                        )

                        released = await release_expired_reservations()
                        if released > 0:
                            logger.info(
                                f"[C07] {released} reservas expiradas liberadas"
                            )
                    except Exception as e:
                        logger.error(f"[C07] Error liberando reservas: {e}")

                await asyncio.sleep(2)

        import asyncio

        if should_run_worker():
            asyncio.create_task(worker_loop())
            logger.info("✅ Worker loop iniciado — procesando cola cada 2 segundos")
        else:
            logger.warning(
                "⚠️ Worker loop deshabilitado (no se detectó Railway y "
                "WORKER_ENABLED no está en true) — este proceso NO procesará "
                "message_jobs. Setea WORKER_ENABLED=true para forzarlo."
            )

    # ------------------------------------------------------------------
    # MIDDLEWARE: Contexto de Tenant (multi-tenant)
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def tenant_context_middleware(request: Request, call_next):
        tenant_identifier = request.headers.get("x-tenant-id")

        if not tenant_identifier:
            path_parts = request.url.path.strip("/").split("/")
            if (
                len(path_parts) >= 3
                and path_parts[0] == "webhook"
                and path_parts[1] == "whatsapp"
            ):
                tenant_identifier = path_parts[2]

        if not tenant_identifier and request.url.path not in PUBLIC_PATHS:
            pass

        if tenant_identifier:
            context = load_tenant_context(tenant_identifier)
            if not context:
                return JSONResponse(
                    {"detail": f"Tenant no encontrado o inactivo: {tenant_identifier}"},
                    status_code=404,
                )
            TenantContextManager.set_current(context)

        try:
            response = await call_next(request)
        finally:
            TenantContextManager.clear()

        return response

    # ------------------------------------------------------------------
    # WhatsApp webhooks en la raíz
    # ------------------------------------------------------------------
    app.include_router(whatsapp_router)

    # Mount /api/v1 sub-app
    api_v1 = create_api_v1(origins)
    app.mount(API_PREFIX, api_v1)

    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "EstructuraAI API. See /api/v1/docs"}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    return app


app = create_app()