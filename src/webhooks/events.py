# -*- coding: utf-8 -*-
"""
events.py - Eventos del Sistema EstructuraAI
=============================================
Define los 8 eventos del sistema y sus payloads.
Integra WebhookManager + WebhookDispatcher para
notificar a los tenants automáticamente.

Eventos:
    1. sale.created          → nueva venta
    2. sale.completed        → venta completada
    3. product.low_stock     → stock bajo
    4. product.out_of_stock  → sin stock
    5. conversation.started  → nueva conversación
    6. conversation.closed   → conversación cerrada
    7. import.completed      → Excel importado
    8. import.failed         → Excel falló

Uso:
    emitter = EventEmitter(manager, dispatcher)
    emitter.sale_created(tenant_id, sale_data)
    emitter.import_completed(tenant_id, import_data)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.logger import logger
from src.webhooks.dispatcher import DeliveryResult, WebhookDispatcher
from src.webhooks.webhook_manager import WebhookManager


# ── Constantes de eventos ─────────────────────────────────────


class EventType:
    """Nombres de los 8 eventos del sistema."""

    SALE_CREATED = "sale.created"
    SALE_COMPLETED = "sale.completed"
    PRODUCT_LOW_STOCK = "product.low_stock"
    PRODUCT_OUT_OF_STOCK = "product.out_of_stock"
    CONVERSATION_STARTED = "conversation.started"
    CONVERSATION_CLOSED = "conversation.closed"
    IMPORT_COMPLETED = "import.completed"
    IMPORT_FAILED = "import.failed"

    @classmethod
    def all(cls) -> List[str]:
        return [
            cls.SALE_CREATED,
            cls.SALE_COMPLETED,
            cls.PRODUCT_LOW_STOCK,
            cls.PRODUCT_OUT_OF_STOCK,
            cls.CONVERSATION_STARTED,
            cls.CONVERSATION_CLOSED,
            cls.IMPORT_COMPLETED,
            cls.IMPORT_FAILED,
        ]


# ── Emisor de eventos ─────────────────────────────────────────


class EventEmitter:
    """
    Emite eventos del sistema y los despacha a webhooks.

    Cada método corresponde a un evento específico con
    su payload tipado y validado.

    Uso:
        emitter = EventEmitter(
            manager    = WebhookManager(supabase),
            dispatcher = WebhookDispatcher(),
        )

        # Cuando se crea una venta
        emitter.sale_created("tenant_a", {
            "sale_id":   "uuid",
            "total":     180_000,
            "product":   "Camara Domo",
            "customer":  "+57300...",
        })

        # Cuando se importa un Excel
        emitter.import_completed("tenant_a", {
            "import_id":    "uuid",
            "saved_count":  25,
            "failed_count": 0,
            "file_name":    "propiedades.xlsx",
        })
    """

    def __init__(
        self,
        manager: WebhookManager,
        dispatcher: WebhookDispatcher,
    ) -> None:
        self._manager = manager
        self._dispatcher = dispatcher

    # ── Eventos de Ventas ────────────────────────────────────

    def sale_created(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando se registra una nueva venta.

        data esperado:
            sale_id:     UUID de la venta
            total:       Monto total
            currency:    "COP"
            product:     Nombre del producto
            quantity:    Cantidad vendida
            customer:    Teléfono del cliente
        """
        return self._emit(tenant_id, EventType.SALE_CREATED, data)

    def sale_completed(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando una venta es completada/pagada.

        data esperado:
            sale_id:        UUID de la venta
            total:          Monto total
            payment_method: "transferencia", "efectivo", etc.
            completed_at:   Timestamp
        """
        return self._emit(tenant_id, EventType.SALE_COMPLETED, data)

    # ── Eventos de Productos ─────────────────────────────────

    def product_low_stock(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando el stock de un producto está bajo.

        data esperado:
            product_id:   UUID del producto
            product_name: Nombre
            current_stock: Stock actual
            min_stock:    Stock mínimo configurado
        """
        return self._emit(tenant_id, EventType.PRODUCT_LOW_STOCK, data)

    def product_out_of_stock(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando un producto se agota.

        data esperado:
            product_id:   UUID del producto
            product_name: Nombre
            last_sale_id: Última venta que agotó el stock
        """
        return self._emit(tenant_id, EventType.PRODUCT_OUT_OF_STOCK, data)

    # ── Eventos de Conversaciones ────────────────────────────

    def conversation_started(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando inicia una nueva conversación.

        data esperado:
            conversation_id: UUID
            customer_phone:  Teléfono del cliente
            platform:        "whatsapp"
            started_at:      Timestamp
        """
        return self._emit(tenant_id, EventType.CONVERSATION_STARTED, data)

    def conversation_closed(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando una conversación se cierra.

        data esperado:
            conversation_id: UUID
            duration_min:    Duración en minutos
            message_count:   Mensajes intercambiados
            outcome:         "sale", "inquiry", "abandoned"
        """
        return self._emit(tenant_id, EventType.CONVERSATION_CLOSED, data)

    # ── Eventos de Importación ───────────────────────────────

    def import_completed(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando un Excel se importa exitosamente.

        data esperado:
            import_id:    UUID de la importación
            file_name:    Nombre del archivo
            saved_count:  Productos guardados
            failed_count: Productos fallidos
            duration_ms:  Tiempo de procesamiento
        """
        return self._emit(tenant_id, EventType.IMPORT_COMPLETED, data)

    def import_failed(
        self,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Emite evento cuando falla la importación de un Excel.

        data esperado:
            import_id:  UUID de la importación
            file_name:  Nombre del archivo
            error:      Descripción del error
            rows_processed: Filas procesadas antes del fallo
        """
        return self._emit(tenant_id, EventType.IMPORT_FAILED, data)

    # ── Core ─────────────────────────────────────────────────

    def _emit(
        self,
        tenant_id: str,
        event_type: str,
        data: Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Obtiene los webhooks listeners y los notifica.

        Args:
            tenant_id:  ID del tenant
            event_type: Tipo de evento
            data:       Datos del evento

        Returns:
            Lista de DeliveryResult (uno por webhook notificado)
        """
        # Agregar timestamp si no viene
        if "timestamp" not in data:
            data["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Buscar webhooks que escuchan este evento
        listeners = self._manager.get_listeners(tenant_id, event_type)

        if not listeners:
            logger.debug(
                f"Evento '{event_type}' sin listeners para " f"tenant='{tenant_id}'"
            )
            return []

        logger.info(
            f"Emitiendo '{event_type}' a {len(listeners)} webhook(s) "
            f"para tenant='{tenant_id}'"
        )

        # Despachar a todos los listeners
        results = self._dispatcher.dispatch_to_all(
            webhooks=listeners,
            event_type=event_type,
            data=data,
        )

        exitosos = sum(1 for r in results if r.success)
        logger.info(
            f"Evento '{event_type}': " f"{exitosos}/{len(results)} webhooks entregados"
        )

        return results
