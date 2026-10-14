from typing import Dict, Any
from src.services.agent_orchestrator import AgentOrchestrator
from src.core.whatsapp_handler import WhatsAppHandler  # ← Cambio 1: core en lugar de integrations
from src.core.logger import logger  # ← Cambio 2: Importar logger


class WhatsAppAgentBridge:
    
    
    def __init__(
        self,
        whatsapp_handler: WhatsAppHandler,
        agent_orchestrator: AgentOrchestrator
    ):
        """
        Inicializa el bridge.
        
        Args:
            whatsapp_handler: Handler de WhatsApp (Daniel)
            agent_orchestrator: Orquestador del agente (Camilo)
        """
        self.whatsapp = whatsapp_handler
        self.agent = agent_orchestrator
        logger.info("WhatsAppAgentBridge inicializado")
    
    async def handle_incoming_message(
        self,
        phone_number: str,
        message_text: str,
        tenant_id: str
    ) -> None:
        """
        Procesa un mensaje entrante de WhatsApp.
        
        Flujo:
        1. WhatsApp recibe mensaje
        2. Agente procesa (async)
        3. Respuesta se envía a WhatsApp (sync)
        
        Args:
            phone_number: Número del usuario (con +57)
            message_text: Texto del mensaje
            tenant_id: ID del tenant
        """
        try:
            logger.info(
                f"Procesando mensaje WhatsApp",
                phone=phone_number,
                tenant=tenant_id,
                message_preview=message_text[:50]
            )
            
            # 1. Procesar con agente (ASYNC)
            conversation_id = f"wa_{tenant_id}_{phone_number}"
            
            response: Dict[str, Any] = await self.agent.process_message(
                message=message_text,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                metadata={
                    "source": "whatsapp",
                    "phone_number": phone_number
                }
            )
            
            logger.info(
                f"Agente generó respuesta",
                conversation_id=conversation_id,
                intent=response.get("intent")
            )
            
            # 2. Enviar respuesta por WhatsApp (SYNC)
            # NOTA: El método send_message de Daniel NO es async
            # Eliminar el número de país (+57) si está presente
            to_number = phone_number.replace("+", "")
            
            await self.whatsapp.send_message(
                phone_number=to_number,
                message=response["response"]
            )
            
            logger.success(
                f"Respuesta enviada a WhatsApp",
                phone=phone_number
            )
            
            # 3. Si hay productos, enviar imágenes (máximo 3)
            if response.get("products"):
                productos_con_imagen = [
                    p for p in response["products"]
                    if p.get("image_url")
                ]
                for producto in productos_con_imagen[:3]:
                    await self.whatsapp.send_image(
                        phone_number=to_number,
                        image_url=producto["image_url"],
                        caption=producto.get("name")
                    )
                logger.info(
                    f"Productos en respuesta (envío de imágenes realizado)",
                    count=len(productos_con_imagen[:3])
                )
        
        except Exception as e:
            logger.error(
                f"Error en bridge WhatsApp-Agente: {e}",
                phone=phone_number,
                tenant=tenant_id,
                exc_info=True
            )
            
            # Respuesta de fallback
            await self._send_error_fallback(phone_number)
    
    async def _send_error_fallback(self, phone_number: str) -> None:
        """
        Envía mensaje de error genérico al usuario.
        
        Args:
            phone_number: Número del usuario
        """
        try:
            to_number = phone_number.replace("+", "")
            
            await self.whatsapp.send_message(
                phone_number=to_number,
                message="Disculpa, tuve un problema técnico. ¿Puedes repetir tu mensaje?"
            )
        except Exception as e:
            logger.error(
                f"Error enviando fallback: {e}",
                phone=phone_number
            )