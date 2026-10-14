# Guía de Troubleshooting para WhatsApp Bot

Esta guía ayuda a diagnosticar y resolver problemas comunes en la integración de WhatsApp Business API con el bot multi-tenant.

---

## Índice
- [Errores de conexión](#errores-de-conexión)
- [Mensajes no enviados](#mensajes-no-enviados)
- [Rate limiting](#rate-limiting)
- [Problemas multi-tenant](#problemas-multi-tenant)
- [Logs y monitoreo](#logs-y-monitoreo)
- [Pruebas y validación](#pruebas-y-validación)

---

## Errores de conexión
**Síntoma:** El bot no responde o muestra errores de conexión.

**Causa posible:**
- Token o phone_id incorrectos en el tenant.
- Webhook no registrado o inaccesible.
- Variable de entorno `WHATSAPP_VERIFY_TOKEN` mal configurada.

**Solución paso a paso:**
1. Verifica el token y phone_id en la configuración del tenant.
2. Revisa la variable de entorno `WHATSAPP_VERIFY_TOKEN`.
3. Asegúrate de que el webhook esté registrado y accesible desde Meta.
4. Consulta los logs para detalles de errores de conexión.

---

## Mensajes no enviados
**Síntoma:** El bot recibe mensajes pero no responde o los mensajes no llegan al usuario.

**Causa posible:**
- Error de envío (`Error enviando mensaje WhatsApp`).
- Número de destino mal formateado.
- Falta de saldo o permisos en WhatsApp Business.
- Rate limiting activo.

**Solución paso a paso:**
1. Revisa los logs para errores de envío.
2. Verifica que el número de destino esté en formato internacional.
3. Confirma que el tenant tiene saldo y permisos activos.
4. Si el mensaje es bloqueado por rate limiting, revisa la sección correspondiente.

---

## Rate limiting
**Síntoma:** El bot responde con mensajes como "🚦 Has enviado demasiados mensajes este minuto" o "🚦 Alcanzaste el límite por hora".

**Causa posible:**
- Se superó el límite de 10 mensajes/minuto o 100/hora por usuario y tenant.

**Solución paso a paso:**
1. Espera el tiempo indicado en el mensaje.
2. Para pruebas, revisa `tests/test_rate_limiter.py`.
3. Recuerda que los límites son independientes por tenant y usuario.

---

## Problemas multi-tenant
**Síntoma:** Un tenant no responde o los mensajes se mezclan entre tenants.

**Causa posible:**
- Token o phone_id compartidos o mal configurados.
- Configuración incorrecta del tenant.

**Solución paso a paso:**
1. Verifica que cada tenant tenga su propio token y phone_id.
2. Revisa la configuración y logs del tenant afectado.
3. Confirma que los mensajes y límites no se mezclan entre tenants.

---

## Logs y monitoreo
Todos los eventos importantes se registran en el logger.
Usa los logs para rastrear errores, duplicados y rate limiting.
Los logs muestran el tenant, usuario y tipo de evento.

### Comandos útiles para debugging
- `tail -f logs/app.log` (Linux/macOS) o `Get-Content .\logs\app.log -Wait` (Windows) para ver logs en tiempo real.
- `python -m pytest -s tests/test_rate_limiter.py` para ver prints y validar el rate limiter.
- `python -m pytest -s tests/test_whatsapp.py` para pruebas de integración.
- `curl -X POST <URL_WEBHOOK> -H "Content-Type: application/json" -d '{...}'` para probar el webhook manualmente.

### Logs a revisar
- Errores de conexión: busca `Error enviando mensaje WhatsApp` o `Error enviando template WhatsApp`.
- Rate limiting: busca mensajes con `Rate limit excedido`.
- Duplicados: busca `Mensaje duplicado ignorado`.
- Configuración: busca `no_tenant_context` o errores de token/phone_id.


### Contacto de soporte
Si nada funciona, contacta al equipo de soporte con:
- Logs relevantes
- Payloads de prueba
- Configuración del tenant
- Descripción del problema

---

## Pruebas y validación
- Ejecuta `pytest -s tests/test_rate_limiter.py` para validar el rate limiter.
- Usa pruebas de integración en `tests/test_whatsapp.py` para validar el flujo completo.
- Verifica los prints y mensajes de feedback en consola.

---

## Contacto y soporte
Si el problema persiste, contacta al equipo de soporte con los logs y detalles del tenant afectados.
