"""
Servicio de notificaciones del sistema.

Centraliza la creación de alertas en la tabla `notifications`.
Cada función representa un evento de negocio específico y es
totalmente defensiva: nunca lanza excepciones al caller.
"""

import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

import requests

from src.config import settings
from src.core.event_bus import event_bus
from src.core.logger import logger


def notify_new_conversation(
    *,
    db_client,
    tenant_id: str,
    customer_phone: str,
    customer_name: Optional[str],
    conversation_id: str,
) -> None:
    """
    Crea una notificación de tipo 'message' cuando un contacto nuevo
    inicia su primera conversación con el bot.

    Se llama solo cuando se CREA una conversación (no en mensajes
    subsiguientes del mismo contacto).

    Args:
        db_client:        Cliente Supabase ya inicializado.
        tenant_id:        ID del tenant dueño de la notificación.
        customer_phone:   Número de WhatsApp del contacto.
        customer_name:    Nombre del contacto (puede ser None).
        conversation_id:  UUID de la conversación recién creada.
    """
    display_name = customer_name.strip() if customer_name else customer_phone

    try:
        db_client.table("notifications").insert(
            {
                "tenant_id": tenant_id,
                "type": "message",
                "title": f"Nuevo cliente: {display_name}",
                "body": (
                    f"{display_name} ({customer_phone}) inició una conversación "
                    f"por WhatsApp."
                ),
                "read_at": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ).execute()

        logger.info(
            f"[NOTIF] Nuevo contacto notificado — "
            f"phone={customer_phone} tenant={tenant_id}"
        )

    except Exception as exc:
        # La notificación es secundaria: nunca debe interrumpir el flujo principal.
        logger.warning(
            f"[NOTIF] No se pudo crear notificación para {customer_phone} "
            f"(tenant={tenant_id}): {exc}"
        )


class NotificationService:
    """Servicio de notificaciones por email y webhook"""

    def __init__(self):
        self.smtp_host = getattr(settings, "SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = getattr(settings, "SMTP_PORT", 587)
        self.smtp_user = getattr(settings, "SMTP_USER", None)
        self.smtp_password = getattr(settings, "SMTP_PASSWORD", None)
        self.from_email = getattr(settings, "FROM_EMAIL", self.smtp_user)
        self.webhook_url = getattr(settings, "ALERT_WEBHOOK_URL", None)
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        event_bus.subscribe("low_stock_alert", self._on_low_stock_alert)
        logger.debug("NotificationService suscrito a eventos")

    def _on_low_stock_alert(self, alert_data: Dict[str, Any]):
        try:
            if self.webhook_url:
                self.send_webhook(alert_data)
            if self.smtp_user and self.smtp_password:
                self.send_email_alert(alert_data)
        except Exception as e:
            logger.error(f"Error al enviar notificación: {e}")

    def send_email_alert(self, alert_data: Dict[str, Any], to_email: str = None) -> bool:
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP no configurado, saltando email")
            return False
        try:
            to = to_email or getattr(settings, "ADMIN_EMAIL", self.smtp_user)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Alerta de Stock Bajo: {alert_data['product_name']}"
            msg["From"] = self.from_email
            msg["To"] = to
            msg.attach(MIMEText(self._generate_email_html(alert_data), "html"))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Email enviado a {to}")
            return True
        except Exception as e:
            logger.error(f"Error al enviar email: {e}")
            return False

    def _generate_email_html(self, alert_data: Dict[str, Any]) -> str:
        severity_color = "#dc3545" if alert_data["severity"] == "critical" else "#ffc107"
        return f"""
        <html><body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="background-color: {severity_color}; color: white; padding: 15px; border-radius: 5px;">
                <h2>Alerta de Stock Bajo</h2>
            </div>
            <div style="margin-top: 20px;">
                <h3>Producto: {alert_data['product_name']}</h3>
                <p><strong>Categoría:</strong> {alert_data.get('category', 'N/A')}</p>
                <p><strong>Stock Actual:</strong> {alert_data['current_stock']} unidades</p>
                <p><strong>Umbral:</strong> {alert_data['threshold']} unidades</p>
                <p><strong>Severidad:</strong> {alert_data['severity'].upper()}</p>
            </div>
        </body></html>
        """

    def send_webhook(self, alert_data: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            logger.warning("Webhook URL no configurada")
            return False
        try:
            payload = {
                "event": "low_stock_alert",
                "severity": alert_data["severity"],
                "product": {
                    "id": alert_data["product_id"],
                    "name": alert_data["product_name"],
                    "category": alert_data.get("category"),
                    "current_stock": alert_data["current_stock"],
                },
                "threshold": alert_data["threshold"],
                "timestamp": alert_data.get("timestamp"),
            }
            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(f"Webhook enviado: {response.status_code}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Error al enviar webhook: {e}")
            return False

    def send_daily_metrics_report(
        self, metrics_data: Dict[str, Any], to_email: str = None
    ) -> bool:
        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP no configurado, saltando reporte diario")
            return False
        try:
            to = to_email or getattr(settings, "ADMIN_EMAIL", self.smtp_user)
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"Reporte Diario de Métricas - {metrics_data.get('date', 'N/A')}"
            msg["From"] = self.from_email
            msg["To"] = to
            msg.attach(MIMEText(self._generate_metrics_report_html(metrics_data), "html"))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            logger.info(f"Reporte diario enviado a {to}")
            return True
        except Exception as e:
            logger.error(f"Error al enviar reporte diario: {e}")
            return False

    def _generate_metrics_report_html(self, metrics_data: Dict[str, Any]) -> str:
        date = metrics_data.get("date", "N/A")
        total_convs = metrics_data.get("total_conversations", 0)
        total_msgs = metrics_data.get("total_messages", 0)
        total_tokens = metrics_data.get("total_tokens_used", 0)
        active_convs = metrics_data.get("active_conversations", 0)
        closed_convs = metrics_data.get("closed_conversations", 0)
        whatsapp = metrics_data.get("whatsapp_conversations", 0)
        web = metrics_data.get("web_conversations", 0)
        telegram = metrics_data.get("telegram_conversations", 0)
        return f"""
        <html><body style="font-family: Arial, sans-serif; padding: 20px;">
            <div style="background-color: #007bff; color: white; padding: 15px; border-radius: 5px;">
                <h2>Reporte Diario de Métricas</h2><p>Fecha: {date}</p>
            </div>
            <div style="margin-top: 20px;">
                <h3>Resumen de Conversaciones</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding:10px;border:1px solid #ddd;"><strong>Total</strong></td><td style="padding:10px;border:1px solid #ddd;">{total_convs}</td></tr>
                    <tr><td style="padding:10px;border:1px solid #ddd;"><strong>Activas</strong></td><td style="padding:10px;border:1px solid #ddd;">{active_convs}</td></tr>
                    <tr><td style="padding:10px;border:1px solid #ddd;"><strong>Cerradas</strong></td><td style="padding:10px;border:1px solid #ddd;">{closed_convs}</td></tr>
                    <tr><td style="padding:10px;border:1px solid #ddd;"><strong>Mensajes</strong></td><td style="padding:10px;border:1px solid #ddd;">{total_msgs}</td></tr>
                    <tr><td style="padding:10px;border:1px solid #ddd;"><strong>Tokens</strong></td><td style="padding:10px;border:1px solid #ddd;">{total_tokens:,}</td></tr>
                </table>
            </div>
            <div style="margin-top: 20px;">
                <h3>Por Plataforma</h3>
                <ul><li>WhatsApp: {whatsapp}</li><li>Web: {web}</li><li>Telegram: {telegram}</li></ul>
            </div>
        </body></html>
        """
