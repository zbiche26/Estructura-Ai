from __future__ import annotations
from typing import List, Optional
from src.core.whatsapp_handler import WhatsAppHandler


def send_text_message(*, to: str, content: str) -> dict:
    """Envía un mensaje de texto por WhatsApp Cloud API."""
    handler = WhatsAppHandler()
    return handler.send_message(to=to, message=content)


def send_template_message(
    *,
    to: str,
    template_name: str,
    language: str = "es",
    params: Optional[List[str]] = None,
) -> dict:
    """
    Envía una plantilla de WhatsApp (fuera de la ventana de 24h).

    Args:
        to: Número de teléfono destino (ej: "+573001234567")
        template_name: Nombre de la plantilla aprobada en Meta
        language: Código de idioma (default: "es")
        params: Lista de parámetros de texto para el body de la plantilla

    Returns:
        Respuesta de la API de Meta
    """
    handler = WhatsAppHandler()

    components = []
    if params:
        components.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": str(p)} for p in params
            ],
        })

    return handler.send_template(
        to=to,
        template_name=template_name,
        language=language,
        components=components,
    )
