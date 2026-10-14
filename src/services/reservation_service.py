"""
Reservation Service — C07: Reserva temporal de productos
=========================================================
El cliente puede apartar un producto por N horas.
Al vencer el tiempo, la reserva se libera automáticamente.

Flujo:
  Cliente pide apartar → crear reserva con expires_at → notificar dueño
  Worker periódico → verificar expiradas → liberar y notificar cliente
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from src.core.logger import logger

# Horas de reserva por defecto (configurable por tenant en agent_config)
DEFAULT_RESERVATION_HOURS = 24

# Keywords que indican intención de reservar/apartar
RESERVATION_KEYWORDS = [
    "apartar",
    "reservar",
    "separar",
    "guardar",
    "lo aparto",
    "lo reservo",
    "lo separo",
    "puedo apartar",
    "puedo reservar",
    "puedo separar",
    "quiero apartar",
    "quiero reservar",
    "quiero separar",
    "ponlo a un lado",
    "guardamelo",
]


def detect_reservation_intent(message: str) -> bool:
    """Detecta si el cliente quiere reservar un producto."""
    message_lower = message.lower()
    for keyword in RESERVATION_KEYWORDS:
        if keyword in message_lower:
            return True
    return False


async def create_reservation(
    tenant_id: str,
    conversation_id: str,
    product_id: str,
    product_name: str,
    hours: int = DEFAULT_RESERVATION_HOURS,
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Crea una reserva temporal del producto.

    Args:
        tenant_id: UUID del tenant
        conversation_id: UUID de la conversación
        product_id: ID del producto en Qdrant
        product_name: Nombre del producto para logs
        hours: Horas que dura la reserva
        notes: Notas adicionales

    Returns:
        Dict con la reserva creada o None si falló
    """
    try:
        from src.core.database import get_db
        import uuid as uuid_module

        db = get_db().client
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=hours)

        # Verificar si ya existe una reserva activa para este producto en esta conversación
        existing = (
            db.table("stock_reservations")
            .select("id, status, expires_at")
            .eq("tenant_id", tenant_id)
            .eq("conversation_id", str(conversation_id))
            .eq("status", "active")
            .execute()
        )

        if existing.data:
            logger.info(
                f"[C07] Ya existe reserva activa para conversación {conversation_id}"
            )
            return existing.data[0]

        # Crear reserva nueva
        # product_id es uuid en la tabla — usamos uuid5 para consistencia con Qdrant
        try:
            product_uuid = str(uuid_module.UUID(product_id))
        except ValueError:
            product_uuid = str(uuid_module.uuid5(uuid_module.NAMESPACE_DNS, product_id))

        result = (
            db.table("stock_reservations")
            .insert(
                {
                    "tenant_id": tenant_id,
                    "conversation_id": str(conversation_id),
                    "product_id": product_uuid,
                    "quantity": 1,
                    "status": "active",
                    "expires_at": expires_at.isoformat(),
                    "notes": notes
                    or f"Reservado por {hours}h vía WhatsApp — {product_name}",
                }
            )
            .execute()
        )

        if result.data:
            reservation = result.data[0]
            logger.info(
                f"[C07] Reserva creada: {reservation['id']} — "
                f"producto '{product_name}' por {hours}h — "
                f"expira: {expires_at.strftime('%d/%m/%Y %H:%M')}"
            )
            return reservation

        return None

    except Exception as e:
        logger.error(f"[C07] Error creando reserva: {e}")
        return None


async def release_expired_reservations(tenant_id: Optional[str] = None) -> int:
    """
    Libera reservas vencidas automáticamente.
    Llamar desde un worker periódico.

    Args:
        tenant_id: Si se especifica, solo libera reservas de ese tenant.
                   Si es None, libera de todos los tenants.

    Returns:
        Número de reservas liberadas
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        now = datetime.now(timezone.utc).isoformat()

        query = (
            db.table("stock_reservations")
            .select("id, tenant_id, conversation_id, notes")
            .eq("status", "active")
            .lt("expires_at", now)
        )

        if tenant_id:
            query = query.eq("tenant_id", tenant_id)

        expired = query.execute()

        if not expired.data:
            return 0

        released_count = 0
        for reservation in expired.data:
            try:
                db.table("stock_reservations").update(
                    {
                        "status": "expired",
                        "released_at": now,
                    }
                ).eq("id", reservation["id"]).execute()

                released_count += 1
                logger.info(f"[C07] Reserva expirada liberada: {reservation['id']}")

            except Exception as e:
                logger.error(f"[C07] Error liberando reserva {reservation['id']}: {e}")

        if released_count > 0:
            logger.info(f"[C07] {released_count} reservas liberadas automáticamente")

        return released_count

    except Exception as e:
        logger.error(f"[C07] Error en release_expired_reservations: {e}")
        return 0


async def get_active_reservation(
    tenant_id: str,
    conversation_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Obtiene la reserva activa de una conversación si existe.
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        result = (
            db.table("stock_reservations")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("conversation_id", str(conversation_id))
            .eq("status", "active")
            .limit(1)
            .execute()
        )

        return result.data[0] if result.data else None

    except Exception as e:
        logger.error(f"[C07] Error obteniendo reserva activa: {e}")
        return None


async def complete_reservation(reservation_id: str) -> bool:
    """
    Marca una reserva como completada (cuando se confirma el pedido).
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        now = datetime.now(timezone.utc).isoformat()
        db.table("stock_reservations").update(
            {
                "status": "completed",
                "completed_at": now,
            }
        ).eq("id", reservation_id).execute()

        logger.info(f"[C07] Reserva completada: {reservation_id}")
        return True

    except Exception as e:
        logger.error(f"[C07] Error completando reserva {reservation_id}: {e}")
        return False
