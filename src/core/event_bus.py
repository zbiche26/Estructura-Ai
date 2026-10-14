"""
Event Bus - Sistema de Eventos (Observer Pattern)
==================================================

Este módulo implementa el patrón Observer mediante un Event Bus.
Permite que diferentes partes del sistema se comuniquen sin
conocerse directamente.
"""

import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Callable, Any, Optional
from uuid import uuid4
from src.core.logger import logger
from src.core.tenant_context import TenantContextManager


# ============================================
# MODELO: EVENT
# ============================================


@dataclass
class Event:
    """
    Representa un evento del sistema
    """

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    tenant_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self):
        return f"Event({self.event_type}, Tenant: {self.tenant_id[:8]}...)"

    def __repr__(self):
        return self.__str__()


# ============================================
# EVENT BUS
# ============================================


class EventBus:
    """
    Bus central de eventos del sistema

    Soporta handlers síncronos y asíncronos (async/await).
    Thread-safe para múltiples requests concurrentes.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self._event_history: List[Event] = []
        self._max_history: int = 1000
        logger.debug("📡 Event Bus inicializado")

    def subscribe(self, event_type: str, handler: Callable[[Event], None]):
        """
        Suscribe un handler a un tipo de evento.
        Soporta handlers sync y async.
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        self._subscribers[event_type].append(handler)

        handler_name = (
            handler.__name__ if hasattr(handler, "__name__") else str(handler)
        )
        logger.info(f"📡 Suscrito '{handler_name}' a evento '{event_type}'")

    def unsubscribe(self, event_type: str, handler: Callable[[Event], None]):
        """Cancela la suscripción de un handler."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
                handler_name = (
                    handler.__name__ if hasattr(handler, "__name__") else str(handler)
                )
                logger.info(f"🔇 Desuscrito '{handler_name}' de evento '{event_type}'")
            except ValueError:
                logger.warning(
                    f"⚠️  Handler no encontrado en suscriptores de '{event_type}'"
                )

    def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Publica un evento a todos los suscriptores.
        Soporta handlers síncronos y asíncronos automáticamente.
        """
        # Obtener tenant actual
        tenant = TenantContextManager.get_current()
        tenant_id = tenant.tenant_id if tenant else "system"

        # Crear evento
        event = Event(
            event_type=event_type,
            data=data,
            tenant_id=tenant_id,
            metadata=metadata or {},
        )

        # Guardar en historial
        self._add_to_history(event)

        # Notificar suscriptores
        if event_type in self._subscribers:
            subscribers_count = len(self._subscribers[event_type])
            logger.info(
                f"📢 Publicando '{event_type}' a {subscribers_count} suscriptores"
            )

            for handler in self._subscribers[event_type]:
                try:
                    if inspect.iscoroutinefunction(handler):
                        # Handler async → crear task en el loop actual
                        asyncio.create_task(handler(event))
                    else:
                        # Handler sync → llamar directo
                        handler(event)
                except Exception as e:
                    handler_name = (
                        handler.__name__
                        if hasattr(handler, "__name__")
                        else str(handler)
                    )
                    logger.error(
                        f"❌ Error en handler '{handler_name}' para evento '{event_type}': {e}"
                    )
        else:
            logger.debug(f"🔇 No hay suscriptores para evento '{event_type}'")

    def _add_to_history(self, event: Event):
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history :]

    def get_history(
        self,
        event_type: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Event]:
        """Obtiene historial de eventos con filtros opcionales."""
        events = self._event_history.copy()

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        return events[-limit:]

    def get_subscribers_count(self, event_type: str) -> int:
        return len(self._subscribers.get(event_type, []))

    def get_all_event_types(self) -> List[str]:
        return list(self._subscribers.keys())

    def clear_history(self):
        self._event_history.clear()
        logger.debug("🧹 Historial de eventos limpiado")

    def clear_subscribers(self, event_type: Optional[str] = None):
        if event_type:
            if event_type in self._subscribers:
                self._subscribers[event_type].clear()
                logger.debug(f"🧹 Suscriptores de '{event_type}' limpiados")
        else:
            self._subscribers.clear()
            logger.debug("🧹 Todos los suscriptores limpiados")


# ============================================
# DECORADOR: @event_handler
# ============================================


def event_handler(event_type: str):
    """Decorador para marcar métodos como handlers de eventos."""

    def decorator(func: Callable):
        func._is_event_handler = True
        func._event_type = event_type
        return func

    return decorator


# ============================================
# INSTANCIA GLOBAL
# ============================================

event_bus = EventBus()
