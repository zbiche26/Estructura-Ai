"""
Order Service — C05: Flujo de compra guiado
============================================
Extrae datos del pedido del historial de conversación y los guarda en order_requests.
Notifica al dueño cuando el pedido está confirmado.

Flujo:
  producto → talla/color → método de pago → dirección → confirmación → guardar → notificar
"""

from typing import Optional, Dict, Any
from src.core.logger import logger

# Métodos de pago aceptados
PAYMENT_METHODS = ["nequi", "daviplata", "transferencia", "efectivo", "contraentrega"]

# Keywords que indican confirmación del pedido
CONFIRMATION_KEYWORDS = [
    "sí",
    "si",
    "confirmo",
    "confirmado",
    "dale",
    "listo",
    "ok",
    "de acuerdo",
    "perfecto",
    "acepto",
    "correcto",
    "así es",
    "eso es",
    "exacto",
    "vamos",
    "hagámoslo",
]


def extract_order_data_from_history(history: list) -> Dict[str, Any]:
    """
    Extrae datos del pedido del historial de conversación.
    Busca producto, talla, color, método de pago y dirección
    en los mensajes del usuario.

    Args:
        history: Lista de {role, content} del historial

    Returns:
        Dict con los datos extraídos del pedido
    """
    order_data = {
        "producto": None,
        "talla": None,
        "color": None,
        "metodo_pago": None,
        "direccion": None,
        "confirmado": False,
    }

    for msg in history:
        if msg.get("role") != "user":
            continue

        content = msg.get("content", "").lower().strip()

        # Detectar talla
        if not order_data["talla"]:
            for talla in [
                "xs",
                "s",
                "m",
                "l",
                "xl",
                "xxl",
                "talla 6",
                "talla 8",
                "talla 10",
                "talla 12",
                "talla 14",
                "6",
                "8",
                "10",
                "12",
                "14",
            ]:
                if talla in content:
                    order_data["talla"] = talla.upper()
                    break

        # Detectar método de pago
        if not order_data["metodo_pago"]:
            for method in PAYMENT_METHODS:
                if method in content:
                    order_data["metodo_pago"] = method
                    break

        # Detectar confirmación
        for keyword in CONFIRMATION_KEYWORDS:
            if keyword in content:
                order_data["confirmado"] = True
                break

    return order_data


def is_order_complete(order_data: Dict[str, Any]) -> bool:
    """
    Verifica si el pedido tiene todos los datos requeridos.
    producto y método de pago son obligatorios.
    talla es obligatoria solo si el producto la requiere.
    """
    return bool(
        order_data.get("producto")
        and order_data.get("metodo_pago")
        and order_data.get("confirmado")
    )


async def save_order(
    tenant_id: str,
    conversation_id: str,
    order_data: Dict[str, Any],
) -> Optional[str]:
    """
    Guarda el pedido en order_requests.

    Args:
        tenant_id: UUID del tenant
        conversation_id: UUID de la conversación
        order_data: Datos del pedido extraídos

    Returns:
        ID del pedido creado o None si falló
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        result = (
            db.table("order_requests")
            .insert(
                {
                    "tenant_id": tenant_id,
                    "conversation_id": conversation_id,
                    "producto": order_data.get("producto", ""),
                    "talla": order_data.get("talla"),
                    "color": order_data.get("color"),
                    "metodo_pago": order_data.get("metodo_pago"),
                    "direccion": order_data.get("direccion"),
                    "status": "pending",
                }
            )
            .execute()
        )

        if result.data:
            order_id = result.data[0]["id"]
            logger.info(f"[C05] Pedido guardado: {order_id} — tenant {tenant_id}")
            return order_id

        return None

    except Exception as e:
        logger.error(f"[C05] Error guardando pedido: {e}")
        return None


async def notify_owner_new_order(
    tenant_id: str,
    order_data: Dict[str, Any],
    customer_phone: Optional[str],
    customer_name: Optional[str],
    order_id: Optional[str],
) -> None:
    """
    Notifica al dueño por WhatsApp cuando hay un pedido nuevo confirmado.
    Lee owner_phone desde agent_config.
    """
    try:
        from src.core.database import get_db

        db = get_db().client

        result = (
            db.table("agent_config")
            .select("owner_phone, nombre_agente")
            .eq("tenant_id", tenant_id)
            .limit(1)
            .execute()
        )

        if not result.data or not result.data[0].get("owner_phone"):
            logger.warning(f"[C05] owner_phone no configurado para tenant {tenant_id}")
            return

        owner_phone = result.data[0]["owner_phone"]
        agent_name = result.data[0].get("nombre_agente", "El agente")
        customer_info = customer_name or customer_phone or "Cliente"

        notification = (
            f"🛍️ *Nuevo pedido confirmado*\n\n"
            f"*Cliente:* {customer_info}\n"
            f"*Teléfono:* {customer_phone or 'No disponible'}\n"
            f"*Producto:* {order_data.get('producto', 'N/A')}\n"
            f"*Talla:* {order_data.get('talla', 'N/A')}\n"
            f"*Color:* {order_data.get('color', 'N/A')}\n"
            f"*Método de pago:* {order_data.get('metodo_pago', 'N/A')}\n"
            f"*Dirección:* {order_data.get('direccion', 'Recoge en tienda')}\n"
            f"*ID Pedido:* {str(order_id)[:8] if order_id else 'N/A'}...\n\n"
            f"Capturado por {agent_name} vía WhatsApp."
        )

        from src.core.whatsapp_handler import WhatsAppHandler

        handler = WhatsAppHandler()
        handler.send_message(to=owner_phone, message=notification)

        logger.info(f"[C05] Notificación de pedido enviada al dueño: {owner_phone}")

    except Exception as e:
        logger.error(f"[C05] Error notificando pedido al dueño: {e}")
