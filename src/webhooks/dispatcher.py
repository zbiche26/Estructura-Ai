# -*- coding: utf-8 -*-
"""
dispatcher.py - Dispatcher de Webhooks
=======================================
Envía payloads HTTP POST a los endpoints registrados.
Incluye retry automático, firma HMAC-SHA256 y registro
de entregas.

Características:
    - Retry con backoff exponencial (3 intentos)
    - Firma HMAC-SHA256 en header X-Signature-256
    - Timeout configurable
    - Registro de cada intento en delivery_log
    - Modo dry_run para tests

Uso:
    dispatcher = WebhookDispatcher()
    result = dispatcher.dispatch(webhook, event_type, data)
    print(result.success)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from src.core.logger import logger
from src.webhooks.webhook_manager import WebhookRecord


# ── Value Objects ────────────────────────────────────────────

@dataclass
class DeliveryResult:
    """
    Resultado de un intento de entrega.

    Attributes:
        delivery_id:    UUID de esta entrega
        webhook_id:     ID del webhook
        tenant_id:      ID del tenant
        event_type:     Tipo de evento
        success:        Si fue exitoso
        status_code:    HTTP status code recibido
        attempts:       Número de intentos realizados
        duration_ms:    Duración total en ms
        error:          Mensaje de error si falló
        delivered_at:   Timestamp de entrega exitosa
    """
    delivery_id:  str  = ""
    webhook_id:   str  = ""
    tenant_id:    str  = ""
    event_type:   str  = ""
    success:      bool = False
    status_code:  int  = 0
    attempts:     int  = 0
    duration_ms:  float = 0.0
    error:        str  = ""
    delivered_at: str  = ""

    def __repr__(self) -> str:
        return (
            f"DeliveryResult("
            f"event='{self.event_type}', "
            f"success={self.success}, "
            f"attempts={self.attempts}, "
            f"status={self.status_code})"
        )


# ── Dispatcher principal ─────────────────────────────────────

class WebhookDispatcher:
    """
    Envía webhooks con retry y firma HMAC.

    Flujo por cada dispatch:
        1. Construir payload con metadata del evento
        2. Firmar payload con secret del webhook
        3. Enviar HTTP POST con headers de seguridad
        4. Si falla, reintentar con backoff exponencial
        5. Registrar resultado en delivery_log

    Uso:
        dispatcher = WebhookDispatcher(timeout=10, max_retries=3)

        result = dispatcher.dispatch(
            webhook    = webhook_record,
            event_type = "sale.created",
            data       = {"sale_id": "123", "total": 180000},
        )

        if not result.success:
            print(f"Falló: {result.error}")
    """

    def __init__(
        self,
        timeout:     int  = 10,
        max_retries: int  = 3,
        dry_run:     bool = False,
    ) -> None:
        """
        Args:
            timeout:     Segundos de timeout por request
            max_retries: Intentos máximos antes de desistir
            dry_run:     Si True, simula sin hacer HTTP real
        """
        self._timeout     = timeout
        self._max_retries = max_retries
        self._dry_run     = dry_run
        self._delivery_log: List[DeliveryResult] = []

    # ── API pública ──────────────────────────────────────────

    def dispatch(
        self,
        webhook:    WebhookRecord,
        event_type: str,
        data:       Dict[str, Any],
    ) -> DeliveryResult:
        """
        Envía el evento al endpoint del webhook.

        Args:
            webhook:    WebhookRecord con URL y secret
            event_type: Tipo de evento (ej: "sale.created")
            data:       Datos del evento

        Returns:
            DeliveryResult con el resultado del envío
        """
        delivery_id = str(uuid.uuid4())
        start_time  = time.time()

        result = DeliveryResult(
            delivery_id = delivery_id,
            webhook_id  = webhook.id,
            tenant_id   = webhook.tenant_id,
            event_type  = event_type,
        )

        # Construir payload
        payload = self._build_payload(
            event_type  = event_type,
            data        = data,
            delivery_id = delivery_id,
            tenant_id   = webhook.tenant_id,
        )
        payload_str = json.dumps(payload, ensure_ascii=False)

        # Construir headers
        headers = self._build_headers(webhook, payload_str)

        logger.info(
            f"Dispatching '{event_type}' → {webhook.url} "
            f"(delivery_id={delivery_id})"
        )

        # Intentar envío con retry
        for attempt in range(1, self._max_retries + 1):
            result.attempts = attempt
            try:
                status_code, response_body = self._send(
                    url     = webhook.url,
                    payload = payload_str,
                    headers = {**headers, **webhook.headers},
                )

                if 200 <= status_code < 300:
                    result.success      = True
                    result.status_code  = status_code
                    result.delivered_at = datetime.now(
                        timezone.utc
                    ).isoformat()
                    logger.success(
                        f"Webhook entregado: '{event_type}' → "
                        f"{webhook.url} ({status_code}) "
                        f"intento {attempt}"
                    )
                    break
                else:
                    result.status_code = status_code
                    result.error       = (
                        f"HTTP {status_code} en intento {attempt}"
                    )
                    logger.warning(
                        f"Webhook falló: HTTP {status_code} "
                        f"intento {attempt}/{self._max_retries}"
                    )

            except Exception as exc:
                result.error = str(exc)
                logger.warning(
                    f"Error enviando webhook intento "
                    f"{attempt}/{self._max_retries}: {exc}"
                )

            # Backoff exponencial antes del siguiente intento
            if attempt < self._max_retries:
                wait = 2 ** (attempt - 1)  # 1s, 2s, 4s
                logger.debug(f"Esperando {wait}s antes del reintento...")
                if not self._dry_run:
                    time.sleep(wait)

        result.duration_ms = round((time.time() - start_time) * 1000, 2)
        self._delivery_log.append(result)

        if not result.success:
            logger.error(
                f"Webhook fallido después de {result.attempts} intentos: "
                f"'{event_type}' → {webhook.url}"
            )

        return result

    def dispatch_to_all(
        self,
        webhooks:   List[WebhookRecord],
        event_type: str,
        data:       Dict[str, Any],
    ) -> List[DeliveryResult]:
        """
        Envía el evento a múltiples webhooks.

        Args:
            webhooks:   Lista de webhooks a notificar
            event_type: Tipo de evento
            data:       Datos del evento

        Returns:
            Lista de DeliveryResult
        """
        results = []
        for webhook in webhooks:
            result = self.dispatch(webhook, event_type, data)
            results.append(result)
        return results

    def get_delivery_log(
        self,
        webhook_id: Optional[str] = None,
    ) -> List[DeliveryResult]:
        """
        Retorna el historial de entregas.

        Args:
            webhook_id: Filtrar por webhook específico (opcional)

        Returns:
            Lista de DeliveryResult
        """
        if webhook_id:
            return [
                d for d in self._delivery_log
                if d.webhook_id == webhook_id
            ]
        return list(self._delivery_log)

    def get_stats(self) -> Dict[str, Any]:
        """
        Estadísticas globales del dispatcher.

        Returns:
            Dict con total, exitosos, fallidos, avg_duration_ms
        """
        total    = len(self._delivery_log)
        exitosos = sum(1 for d in self._delivery_log if d.success)
        fallidos = total - exitosos
        avg_ms   = (
            sum(d.duration_ms for d in self._delivery_log) / total
            if total > 0 else 0.0
        )

        return {
            "total":          total,
            "successful":     exitosos,
            "failed":         fallidos,
            "success_rate":   round((exitosos / total) * 100, 2) if total > 0 else 0.0,
            "avg_duration_ms": round(avg_ms, 2),
        }

    # ── Construcción de payload y headers ────────────────────

    def _build_payload(
        self,
        event_type:  str,
        data:        Dict[str, Any],
        delivery_id: str,
        tenant_id:   str,
    ) -> Dict[str, Any]:
        """Construye el payload estándar del webhook."""
        return {
            "id":         delivery_id,
            "event":      event_type,
            "tenant_id":  tenant_id,
            "data":       data,
            "timestamp":  datetime.now(timezone.utc).isoformat(),
            "version":    "1.0",
        }

    def _build_headers(
        self,
        webhook:     WebhookRecord,
        payload_str: str,
    ) -> Dict[str, str]:
        """Construye headers con firma HMAC."""
        signature = hmac.new(
            webhook.secret.encode(),
            payload_str.encode(),
            hashlib.sha256,
        ).hexdigest()

        return {
            "Content-Type":        "application/json",
            "X-Signature-256":     f"sha256={signature}",
            "X-Webhook-Event":     "",  # se llena en dispatch
            "X-EstructuraAI-Event": "",
            "User-Agent":          "EstructuraAI-Webhooks/1.0",
        }

    # ── HTTP ─────────────────────────────────────────────────

    def _send(
        self,
        url:     str,
        payload: str,
        headers: Dict[str, str],
    ) -> tuple[int, str]:
        """
        Envía el HTTP POST.

        En dry_run simula una respuesta exitosa.
        En producción usa httpx o requests.

        Returns:
            Tupla (status_code, response_body)
        """
        if self._dry_run:
            logger.debug(f"[dry_run] POST → {url}")
            return 200, '{"ok": true}'

        try:
            import httpx
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    content = payload.encode("utf-8"),
                    headers = headers,
                )
                return response.status_code, response.text
        except ImportError:
            # Fallback a requests si no hay httpx
            import requests
            response = requests.post(
                url,
                data    = payload.encode("utf-8"),
                headers = headers,
                timeout = self._timeout,
            )
            return response.status_code, response.text