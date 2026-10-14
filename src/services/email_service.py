import os
import smtplib
from email.message import EmailMessage


def send_reset_email(to_email: str, reset_link: str) -> None:
    """Envía el correo de restablecimiento de contraseña vía SMTP (síncrono)."""
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_SENDER", "no-reply@estructuraai.com")

    if not host or not user or not password:
        raise RuntimeError("SMTP no configurado: define SMTP_HOST, SMTP_USER, SMTP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = "Recupera tu contraseña - EstructuraAI"
    msg.set_content(
        f"Hola,\n\nPara restablecer tu contraseña haz clic en el siguiente enlace:\n\n{reset_link}\n\n"
        "Si no solicitaste esto, ignora este correo."
    )

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
