# -*- coding: utf-8 -*-
"""
webhook_manager.py - Gestión de Webhooks por Tenant
=====================================================
CRUD completo de webhooks. Cada tenant puede registrar
URLs externas para recibir notificaciones de eventos.

Eventos soportados:
    - sale.created          → nueva venta registrada
    - sale.completed        → venta completada/pagada
    - product.low_stock     → stock bajo
    - product.out_of_stock  → sin stock
    - conversation.started  → nueva conversación
    - conversation.closed   → conversación cerrada
    - import.completed      → Excel importado
    - import.failed         → Excel falló

Uso:
    manager = WebhookManager(supabase_client)
    webhook = manager.create(tenant_id, WebhookConfig(...))
    manager.trigger(tenant_id, "sale.created", data)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Eventos disponibles ───────────────────────────────────────

WEBHOOK_EVENTS = [
    "sale.created",
    "sale.completed",
    "product.low_stock",
    "product.out_of_stock",
    "conversation.started",
    "conversation.closed",
    "import.completed",
    "import.failed",
]


# ── Value Objects ────────────────────────────────────────────


@dataclass
class WebhookConfig:
    """
    Configuración para crear un webhook.

    Attributes:
        name:        Nombre descriptivo
        url:         URL del endpoint externo
        events:      Lista de eventos a escuchar
        description: Descripción opcional
        headers:     Headers personalizados para enviar
        is_active:   Si está activo (default: True)
    """

    name: str
    url: str
    events: List[str]
    description: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    is_active: bool = True

    def validate(self) -> List[str]:
        """
        Valida la configuración.

        Returns:
            Lista de errores (vacía si es válido)
        """
        errors = []

        if not self.name or not self.name.strip():
            errors.append("El nombre es requerido")

        if not self.url or not self.url.strip():
            errors.append("La URL es requerida")
        elif not self.url.startswith(("http://", "https://")):
            errors.append("La URL debe comenzar con http:// o https://")

        if not self.events:
            errors.append("Debe especificar al menos un evento")
        else:
            invalid = [e for e in self.events if e not in WEBHOOK_EVENTS]
            if invalid:
                errors.append(
                    f"Eventos inválidos: {', '.join(invalid)}. "
                    f"Válidos: {', '.join(WEBHOOK_EVENTS)}"
                )

        return errors


@dataclass
class WebhookRecord:
    """
    Registro completo de un webhook guardado.

    Attributes:
        id:         UUID del webhook
        tenant_id:  Tenant propietario
        name:       Nombre
        url:        URL del endpoint
        secret:     Secret para firma HMAC (generado automáticamente)
        events:     Eventos suscritos
        is_active:  Si está activo
        created_at: Fecha de creación
        updated_at: Última actualización
    """

    id: str
    tenant_id: str
    name: str
    url: str
    secret: str
    events: List[str]
    description: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    def sign_payload(self, payload: str) -> str:
        """
        Genera firma HMAC-SHA256 para el payload.

        Args:
            payload: String JSON del payload

        Returns:
            Firma en formato "sha256=<hex>"
        """
        signature = hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={signature}"

    def listens_to(self, event: str) -> bool:
        """Retorna True si el webhook escucha este evento."""
        return event in self.events

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "url": self.url,
            "secret": self.secret,
            "events": self.events,
            "description": self.description,
            "headers": self.headers,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self) -> str:
        return (
            f"WebhookRecord(name='{self.name}', "
            f"url='{self.url}', "
            f"events={self.events})"
        )


# ── Manager principal ────────────────────────────────────────


class WebhookManager:
    """
    Gestiona el ciclo de vida de webhooks por tenant.

    Usa Supabase como almacenamiento. En modo dry_run
    usa un store en memoria para tests.

    Uso:
        manager = WebhookManager(supabase_client)

        # Crear webhook
        webhook = manager.create("tenant_a", WebhookConfig(
            name   = "Notificar ventas",
            url    = "https://mi-servidor.com/webhooks",
            events = ["sale.created", "sale.completed"],
        ))
        print(webhook.secret)  # guardar para verificar firmas

        # Listar webhooks del tenant
        webhooks = manager.list("tenant_a")

        # Obtener webhooks que escuchan un evento
        listeners = manager.get_listeners("tenant_a", "sale.created")
    """

    def __init__(
        self,
        supabase_client: Any = None,
        dry_run: bool = False,
    ) -> None:
        self._supabase = supabase_client
        self._dry_run = dry_run
        self._store: Dict[str, WebhookRecord] = {}  # para dry_run

    # ── CRUD ─────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        config: WebhookConfig,
    ) -> WebhookRecord:
        """
        Crea un nuevo webhook para el tenant.

        Args:
            tenant_id: ID del tenant
            config:    Configuración del webhook

        Returns:
            WebhookRecord creado con secret generado

        Raises:
            ValueError si la configuración es inválida
        """
        errors = config.validate()
        if errors:
            raise ValueError(f"Configuración inválida: {'; '.join(errors)}")

        now = datetime.now(timezone.utc).isoformat()
        webhook = WebhookRecord(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=config.name.strip(),
            url=config.url.strip(),
            secret=self._generate_secret(),
            events=config.events,
            description=config.description,
            headers=config.headers,
            is_active=config.is_active,
            created_at=now,
            updated_at=now,
        )

        if self._dry_run:
            self._store[webhook.id] = webhook
            return webhook

        self._save_to_supabase(webhook)
        return webhook

    def get(self, webhook_id: str, tenant_id: str) -> Optional[WebhookRecord]:
        """
        Obtiene un webhook por ID verificando que pertenece al tenant.

        Returns:
            WebhookRecord o None si no existe
        """
        if self._dry_run:
            w = self._store.get(webhook_id)
            if w and w.tenant_id == tenant_id:
                return w
            return None

        return self._load_from_supabase(webhook_id, tenant_id)

    def list(
        self,
        tenant_id: str,
        active_only: bool = False,
    ) -> List[WebhookRecord]:
        """
        Lista todos los webhooks del tenant.

        Args:
            tenant_id:   ID del tenant
            active_only: Si True, solo retorna activos

        Returns:
            Lista de WebhookRecord
        """
        if self._dry_run:
            result = [w for w in self._store.values() if w.tenant_id == tenant_id]
            if active_only:
                result = [w for w in result if w.is_active]
            return result

        return self._list_from_supabase(tenant_id, active_only)

    def update(
        self,
        webhook_id: str,
        tenant_id: str,
        updates: Dict[str, Any],
    ) -> Optional[WebhookRecord]:
        """
        Actualiza parcialmente un webhook.

        Args:
            webhook_id: ID del webhook
            tenant_id:  ID del tenant (verificación de propiedad)
            updates:    Dict con campos a actualizar

        Returns:
            WebhookRecord actualizado o None si no existe
        """
        webhook = self.get(webhook_id, tenant_id)
        if not webhook:
            return None

        # Aplicar updates permitidos
        allowed = {"name", "url", "events", "description", "headers", "is_active"}
        for key, value in updates.items():
            if key in allowed:
                setattr(webhook, key, value)

        webhook.updated_at = datetime.now(timezone.utc).isoformat()

        if self._dry_run:
            self._store[webhook_id] = webhook
            return webhook

        self._update_in_supabase(webhook)
        return webhook

    def delete(self, webhook_id: str, tenant_id: str) -> bool:
        """
        Elimina un webhook.

        Returns:
            True si fue eliminado, False si no existía
        """
        webhook = self.get(webhook_id, tenant_id)
        if not webhook:
            return False

        if self._dry_run:
            del self._store[webhook_id]
            return True

        return self._delete_from_supabase(webhook_id, tenant_id)

    def get_listeners(
        self,
        tenant_id: str,
        event: str,
    ) -> List[WebhookRecord]:
        """
        Retorna webhooks activos que escuchan un evento específico.

        Args:
            tenant_id: ID del tenant
            event:     Evento a buscar (ej: "sale.created")

        Returns:
            Lista de webhooks que deben ser notificados
        """
        all_webhooks = self.list(tenant_id, active_only=True)
        return [w for w in all_webhooks if w.listens_to(event)]

    # ── Helpers ──────────────────────────────────────────────

    def _generate_secret(self) -> str:
        """Genera un secret seguro para firmar payloads."""
        return f"whsec_{secrets.token_hex(32)}"

    # ── Supabase ─────────────────────────────────────────────

    def _save_to_supabase(self, webhook: WebhookRecord) -> None:
        if not self._supabase:
            return
        self._supabase.table("webhooks").insert(webhook.to_dict()).execute()

    def _load_from_supabase(
        self, webhook_id: str, tenant_id: str
    ) -> Optional[WebhookRecord]:
        if not self._supabase:
            return None
        try:
            resp = (
                self._supabase.table("webhooks")
                .select("*")
                .eq("id", webhook_id)
                .eq("tenant_id", tenant_id)
                .single()
                .execute()
            )
            return self._from_dict(resp.data) if resp.data else None
        except Exception:
            return None

    def _list_from_supabase(
        self, tenant_id: str, active_only: bool
    ) -> List[WebhookRecord]:
        if not self._supabase:
            return []
        try:
            query = (
                self._supabase.table("webhooks").select("*").eq("tenant_id", tenant_id)
            )
            if active_only:
                query = query.eq("is_active", True)
            resp = query.execute()
            return [self._from_dict(r) for r in (resp.data or [])]
        except Exception:
            return []

    def _update_in_supabase(self, webhook: WebhookRecord) -> None:
        if not self._supabase:
            return
        self._supabase.table("webhooks").update(webhook.to_dict()).eq(
            "id", webhook.id
        ).execute()

    def _delete_from_supabase(self, webhook_id: str, tenant_id: str) -> bool:
        if not self._supabase:
            return False
        try:
            self._supabase.table("webhooks").delete().eq("id", webhook_id).eq(
                "tenant_id", tenant_id
            ).execute()
            return True
        except Exception:
            return False

    def _from_dict(self, data: Dict) -> WebhookRecord:
        return WebhookRecord(
            id=data["id"],
            tenant_id=data["tenant_id"],
            name=data["name"],
            url=data["url"],
            secret=data["secret"],
            events=data.get("events", []),
            description=data.get("description", ""),
            headers=data.get("headers", {}),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
