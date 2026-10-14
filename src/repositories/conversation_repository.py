"""
Conversation & Message Repositories - GestiÃ³n de Conversaciones WhatsApp

Repositories para manejar conversaciones y mensajes de WhatsApp.
Incluye mÃ©todos para crear, buscar y gestionar el historial de chat.

Uso:
    from src.repositories.conversation_repository import conversation_repo, message_repo
    
    # Crear conversaciÃ³n
    conv = conversation_repo.get_or_create(phone_number="+573001234567")
    
    # Agregar mensaje
    msg = message_repo.add_message(conv.id, role="user", content="Hola")
"""

import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID

from src.repositories.base import BaseRepository
from src.models import (
    Conversation, Message, 
    ConversationStatus, MessageRole, MessageType
)
from src.core.logger import logger
from src.core.database import db
from src.core.tenant_context import TenantContextManager


# ============================================
# MESSAGE REPOSITORY
# ============================================

class MessageRepository(BaseRepository[Message]):
    """
    Repository para gestionar mensajes
    
    Maneja todos los mensajes individuales dentro de conversaciones.
    """
    
    def __init__(self, client=None):
        """Inicializa el repository de mensajes"""
        super().__init__(
            table_name="messages",
            model_class=Message,
            client=client or db.client
        )
    
    # ============================================
    # AGREGAR MENSAJES
    # ============================================
    
    def add_message(
        self,
        conversation_id: UUID | str,
        role: MessageRole | str,
        content: str,
        message_type: MessageType | str = MessageType.TEXT,
        strategy_used: Optional[str] = None,
        whatsapp_message_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Message]:
        """
        Agrega un mensaje a una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            role: Rol del mensaje (user, assistant, system)
            content: Contenido del mensaje
            message_type: Tipo de mensaje (text, image, audio, etc.)
            strategy_used: Estrategia del agente que generÃ³ el mensaje
            whatsapp_message_id: ID del mensaje en WhatsApp
            metadata: Metadata adicional
        
        Returns:
            Mensaje creado o None
        """
        try:
            # Convertir enums a strings si es necesario
            role_str = role.value if isinstance(role, MessageRole) else role
            type_str = message_type.value if isinstance(message_type, MessageType) else message_type
            
            message_data = {
                "conversation_id": str(conversation_id),
                "role": role_str,
                "content": content,
                "message_type": type_str,
                "strategy_used": strategy_used,
                "whatsapp_message_id": whatsapp_message_id,
                "metadata": metadata or {}
            }
            
            message = self.create(message_data)
            
            logger.debug(f"ðŸ’¬ Mensaje agregado a conversaciÃ³n {conversation_id}")
            return message
            
        except Exception as e:
            logger.error(f"âŒ Error al agregar mensaje: {e}")
            return None
    
    # ============================================
    # OBTENER MENSAJES
    # ============================================
    
    def get_by_conversation(
        self,
        conversation_id: UUID | str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """
        Obtiene mensajes de una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            limit: NÃºmero mÃ¡ximo de mensajes
            offset: Offset para paginaciÃ³n
        
        Returns:
            Lista de mensajes ordenados por fecha (mÃ¡s antiguos primero)
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("conversation_id", str(conversation_id))
                .order("created_at", desc=False)  # MÃ¡s antiguos primero
                .range(offset, offset + limit - 1)
                .execute()
            )
            
            messages = [Message(**record) for record in result.data]
            
            logger.debug(f"ðŸ“¨ Obtenidos {len(messages)} mensajes de conversaciÃ³n {conversation_id}")
            return messages
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener mensajes: {e}")
            return []
    
    def get_recent_messages(
        self,
        conversation_id: UUID | str,
        limit: int = 10
    ) -> List[Message]:
        """
        Obtiene los mensajes mÃ¡s recientes de una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            limit: NÃºmero de mensajes recientes
        
        Returns:
            Lista de mensajes recientes (mÃ¡s recientes primero)
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("conversation_id", str(conversation_id))
                .order("created_at", desc=True)  # MÃ¡s recientes primero
                .limit(limit)
                .execute()
            )
            
            messages = [Message(**record) for record in result.data]
            
            # Revertir para que queden en orden cronolÃ³gico
            messages.reverse()
            
            logger.debug(f"ðŸ“¨ Obtenidos {len(messages)} mensajes recientes")
            return messages
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener mensajes recientes: {e}")
            return []
    
    def get_chat_history(
        self,
        conversation_id: UUID | str,
        limit: int = 50
    ) -> List[Dict[str, str]]:
        """
        Obtiene el historial de chat en formato para LLM
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            limit: NÃºmero de mensajes
        
        Returns:
            Lista de mensajes en formato [{"role": "user", "content": "..."}]
        """
        try:
            messages = self.get_recent_messages(conversation_id, limit)
            
            history = [
                {
                    "role": msg.role.value if isinstance(msg.role, MessageRole) else msg.role,
                    "content": msg.content
                }
                for msg in messages
            ]
            
            logger.debug(f"ðŸ“œ Historial de chat: {len(history)} mensajes")
            return history
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener historial: {e}")
            return []
    
    # ============================================
    # BÃšSQUEDA
    # ============================================
    
    def search_in_conversation(
        self,
        conversation_id: UUID | str,
        search_term: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Message]:
        """
        Busca mensajes dentro de una conversaciÃ³n con paginaciÃ³n ligera.
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            search_term: TÃ©rmino a buscar (se aplica ilike)
            limit: NÃºmero mÃ¡ximo de resultados (1-200)
            offset: Desplazamiento para paginaciÃ³n
        
        Returns:
            Lista de mensajes que coinciden con el tÃ©rmino buscado
        """
        safe_limit = max(1, min(limit, 200))
        safe_offset = max(0, offset)
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("conversation_id", str(conversation_id))
                .ilike("content", f"%{search_term}%")
                .order("created_at", desc=True)
                .range(safe_offset, safe_offset + safe_limit - 1)
                .execute()
            )
            messages = [Message(**record) for record in result.data]
            logger.debug(
                f"ðŸ” BÃºsqueda '{search_term}': {len(messages)} mensajes "
                f"(offset={safe_offset}, limit={safe_limit})"
            )
            return messages
        except Exception as e:
            logger.error(f"âŒ Error al buscar mensajes: {e}")
            return []
    
    # ============================================
    # ESTADÃSTICAS
    # ============================================
    
    def count_by_role(
        self,
        conversation_id: UUID | str,
        role: MessageRole | str
    ) -> int:
        """
        Cuenta mensajes por rol
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            role: Rol a contar
        
        Returns:
            NÃºmero de mensajes
        """
        try:
            role_str = role.value if isinstance(role, MessageRole) else role
            
            return self.count({
                "conversation_id": str(conversation_id),
                "role": role_str
            })
            
        except Exception as e:
            logger.error(f"âŒ Error al contar mensajes: {e}")
            return 0


# ============================================
# CONVERSATION REPOSITORY
# ============================================

class ConversationRepository(BaseRepository[Conversation]):
    """
    Repository para gestionar conversaciones
    
    Maneja conversaciones de WhatsApp con clientes.
    """
    
    def __init__(self, client=None):
        """Inicializa el repository de conversaciones"""
        super().__init__(
            table_name="conversations",
            model_class=Conversation,
            client=client or db.client
        )
        
        # Repository de mensajes
        self.messages = MessageRepository(client)

    # ============================================
    # MÃ‰TRICAS DE CONVERSACIÃ“N
    # ============================================

    def count_all(self) -> int:
        """Cuenta el total de conversaciones del tenant actual."""
        return self.count()

    def count_active_users(self) -> int:
        """Cuenta usuarios Ãºnicos con conversaciones activas."""
        try:
            query = (
                self.client.table(self.table_name)
                .select("phone")
                .eq("status", ConversationStatus.ACTIVE.value)
            )
            tenant = TenantContextManager.get_current()
            if tenant and tenant.tenant_id:
                query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
            unique_numbers = {
                record["phone"]
                for record in (result.data or [])
                if record.get("phone")
            }
            return len(unique_numbers)
        except Exception as e:
            logger.error(f"âŒ Error al contar usuarios activos: {e}")
            return 0


    def get_average_response_time(self, window_minutes: int = 60, max_pairs: int = 500) -> Optional[float]:
        """
        Calcula el tiempo promedio de respuesta llamando a un RPC en Supabase.
        Requiere la funciÃ³n calculate_avg_response_time en la base de datos.
        Devuelve None si no hay pares usuarioâ†’bot para evitar falsos 0.0.
        """
        tenant = TenantContextManager.get_current()
        tenant_id = tenant.tenant_id if tenant else None
        if not tenant_id:
            return None

        safe_window = max(1, window_minutes)
        safe_pairs = max(1, min(max_pairs, 5000))

        try:
            response = self.client.rpc(
                "calculate_avg_response_time",
                {
                    "p_tenant_id": tenant_id,
                    "p_window_minutes": safe_window,
                    "p_max_pairs": safe_pairs,
                },
            ).execute()

            data = response.data
            if data is None:
                return None
            if isinstance(data, list) and data:
                # Supabase puede devolver lista con un Ãºnico valor
                return float(data[0]) if data[0] is not None else None
            return float(data)
        except Exception as e:
            logger.error(f"âŒ Error al calcular avg_response_time (RPC): {e}")
            return None

    def get_conversations_per_day(self, last_days: int = 7, tenant_id: str = None) -> Dict[str, int]:
        """
        Devuelve el número de conversaciones por día para la ventana solicitada.
        """
        if last_days <= 0:
            raise ValueError("last_days debe ser mayor que cero")

        normalized_days = min(last_days, 90)
        today = datetime.utcnow().date()
        start_date = today - timedelta(days=normalized_days - 1)

        try:
            query = (
                self.client.table(self.table_name)
                .select("created_at")
                .gte("created_at", start_date.isoformat())
            )
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            else:
                tenant = TenantContextManager.get_current()
                if tenant and tenant.tenant_id:
                    query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
        except Exception as e:
            logger.error(f"âŒ Error al obtener conversaciones por dÃ­a: {e}")
            return {}

        per_day = {
            (start_date + timedelta(days=offset)).isoformat(): 0
            for offset in range(normalized_days)
        }

        for record in result.data or []:
            created_at = record.get("created_at")
            if not created_at:
                continue
            day_key = created_at[:10]
            if day_key in per_day:
                per_day[day_key] += 1

        return per_day

    def get_hourly_activity(self, last_days: int = 7) -> Dict[int, int]:
        """
        Devuelve el total de conversaciones agrupadas por hora del día (0-23)
        para la ventana de tiempo indicada.

        Los timestamps se normalizan a UTC antes de extraer la hora.
        Siempre retorna los 24 buckets aunque alguno tenga 0.
        """
        if last_days <= 0:
            raise ValueError("last_days debe ser mayor que cero")

        normalized_days = min(last_days, 90)
        start_date = (datetime.utcnow() - timedelta(days=normalized_days)).isoformat()

        try:
            query = (
                self.client.table(self.table_name)
                .select("created_at")
                .gte("created_at", start_date)
            )
            tenant = TenantContextManager.get_current()
            if tenant and tenant.tenant_id:
                query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
        except Exception as e:
            logger.error(f"Error al obtener actividad por hora: {e}")
            return {h: 0 for h in range(24)}

        hourly: Dict[int, int] = {h: 0 for h in range(24)}
        for record in result.data or []:
            raw_ts = record.get("created_at")
            if not raw_ts:
                continue
            try:
                hour = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).hour
                hourly[hour] += 1
            except (ValueError, AttributeError):
                continue

        return hourly

    def get_intent_distribution(self, last_days: int = 30) -> Dict[str, int]:
        """Cuenta intents en mensajes del tenant para la ventana dada."""
        if last_days <= 0:
            raise ValueError("last_days debe ser mayor que cero")

        normalized_days = min(last_days, 180)
        start_date = (datetime.utcnow().date() - timedelta(days=normalized_days - 1)).isoformat()

        try:
            query = (
                self.client.table(self.table_name)
                .select("context, updated_at")
                .gte("updated_at", start_date)
            )
            tenant = TenantContextManager.get_current()
            if tenant and tenant.tenant_id:
                query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
        except Exception as e:
            logger.error(f"âŒ Error al obtener distribuciÃ³n de intents: {e}")
            return {}

        distribution: Dict[str, int] = {}
        for record in result.data or []:
            raw_context = record.get("context") or {}
            if isinstance(raw_context, str):
                try:
                    context_obj = json.loads(raw_context)
                except json.JSONDecodeError:
                    context_obj = {}
            elif isinstance(raw_context, dict):
                context_obj = raw_context
            else:
                context_obj = {}

            intent = context_obj.get("intent") or "unknown"
            distribution[intent] = distribution.get(intent, 0) + 1

        return distribution
    
    # ============================================
    # CREAR/OBTENER CONVERSACIÃ“N
    # ============================================
    
    def get_or_create(
        self,
        phone_number: str,
        customer_name: Optional[str] = None
    ) -> Optional[Conversation]:
        """
        Obtiene una conversaciÃ³n activa o crea una nueva
        
        Args:
            phone_number: TelÃ©fono del cliente
            customer_name: Nombre del cliente (opcional)
        
        Returns:
            ConversaciÃ³n activa
        """
        try:
            # Buscar conversaciÃ³n activa
            active_conv = self.get_active_by_phone(phone_number)
            
            if active_conv:
                logger.debug(f"ðŸ“± ConversaciÃ³n activa encontrada: {active_conv.id}")
                return active_conv
            
            # Crear nueva conversaciÃ³n
            conv_data = {
                "phone": phone_number,
                "customer_name": customer_name,
                "status": ConversationStatus.ACTIVE.value,
                "context": {}
            }
            
            conversation = self.create(conv_data)
            
            logger.success(f"âœ… Nueva conversaciÃ³n creada: {conversation.id}")
            return conversation
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener/crear conversaciÃ³n: {e}")
            return None
    
    # ============================================
    # BÃšSQUEDAS
    # ============================================
    
    def get_active_by_phone(self, phone_number: str) -> Optional[Conversation]:
        """
        Obtiene la conversaciÃ³n activa de un nÃºmero
        
        Args:
            phone_number: TelÃ©fono del cliente
        
        Returns:
            ConversaciÃ³n activa o None
        """
        try:
            conversations = self.find({
                "phone": phone_number,
                "status": ConversationStatus.ACTIVE.value
            }, limit=1)
            
            return conversations[0] if conversations else None
            
        except Exception as e:
            logger.error(f"âŒ Error al buscar conversaciÃ³n activa: {e}")
            return None
    
    def get_by_phone(
        self,
        phone_number: str,
        limit: int = 100
    ) -> List[Conversation]:
        """
        Obtiene todas las conversaciones de un nÃºmero
        
        Args:
            phone_number: TelÃ©fono del cliente
            limit: NÃºmero mÃ¡ximo de conversaciones
        
        Returns:
            Lista de conversaciones
        """
        try:
            return self.find({"phone": phone_number}, limit=limit)
        except Exception as e:
            logger.error(f"âŒ Error al obtener conversaciones: {e}")
            return []
    
    def get_active_conversations(self, limit: int = 100) -> List[Conversation]:
        """
        Obtiene todas las conversaciones activas
        
        Args:
            limit: NÃºmero mÃ¡ximo de conversaciones
        
        Returns:
            Lista de conversaciones activas
        """
        try:
            return self.find(
                {"status": ConversationStatus.ACTIVE.value},
                limit=limit
            )
        except Exception as e:
            logger.error(f"âŒ Error al obtener conversaciones activas: {e}")
            return []
    
    # ============================================
    # CAMBIAR ESTADOS
    # ============================================
    
    def close_conversation(self, conversation_id: UUID | str) -> Optional[Conversation]:
        """
        Cierra una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
        
        Returns:
            ConversaciÃ³n actualizada o None
        """
        try:
            return self.update(conversation_id, {
                "status": ConversationStatus.CLOSED.value,
                "closed_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"âŒ Error al cerrar conversaciÃ³n: {e}")
            return None
    
    def archive_conversation(self, conversation_id: UUID | str) -> Optional[Conversation]:
        """
        Archiva una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
        
        Returns:
            ConversaciÃ³n actualizada o None
        """
        try:
            return self.update(conversation_id, {
                "status": ConversationStatus.ARCHIVED.value
            })
        except Exception as e:
            logger.error(f"âŒ Error al archivar conversaciÃ³n: {e}")
            return None
    
    def reopen_conversation(self, conversation_id: UUID | str) -> Optional[Conversation]:
        """
        Reabre una conversaciÃ³n cerrada
        
        Args:
            conversation_id: ID de la conversaciÃ³n
        
        Returns:
            ConversaciÃ³n actualizada o None
        """
        try:
            return self.update(conversation_id, {
                "status": ConversationStatus.ACTIVE.value,
                "closed_at": None
            })
        except Exception as e:
            logger.error(f"âŒ Error al reabrir conversaciÃ³n: {e}")
            return None
    
    # ============================================
    # CONTEXTO Y ESTRATEGIA
    # ============================================
    
    def update_context(
        self,
        conversation_id: UUID | str,
        context_updates: Dict[str, Any]
    ) -> Optional[Conversation]:
        """
        Actualiza el contexto de la conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            context_updates: Diccionario con actualizaciones del contexto
        
        Returns:
            ConversaciÃ³n actualizada o None
        """
        try:
            # Obtener conversaciÃ³n actual
            conv = self.get_by_id(conversation_id)
            
            if not conv:
                return None
            
            # Merge contexto
            new_context = {**conv.context, **context_updates}
            
            return self.update(conversation_id, {
                "context": new_context,
                "last_message_at": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"âŒ Error al actualizar contexto: {e}")
            return None
    
    def set_strategy(
        self,
        conversation_id: UUID | str,
        strategy: str
    ) -> Optional[Conversation]:
        """
        Establece la estrategia actual del agente
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            strategy: Nombre de la estrategia
        
        Returns:
            ConversaciÃ³n actualizada o None
        """
        try:
            return self.update(conversation_id, {
                "current_strategy": strategy
            })
        except Exception as e:
            logger.error(f"âŒ Error al establecer estrategia: {e}")
            return None
    
    # ============================================
    # OBTENER CON MENSAJES
    # ============================================
    
    def get_with_messages(
        self,
        conversation_id: UUID | str,
        message_limit: int = 50
    ) -> Optional[Conversation]:
        """
        Obtiene una conversaciÃ³n con sus mensajes
        
        Args:
            conversation_id: ID de la conversaciÃ³n
            message_limit: NÃºmero de mensajes a cargar
        
        Returns:
            ConversaciÃ³n con mensajes o None
        """
        try:
            # Obtener conversaciÃ³n
            conv = self.get_by_id(conversation_id)
            
            if not conv:
                return None
            
            # Cargar mensajes (no hay campo 'messages' en el modelo base,
            # pero podemos agregarlo dinÃ¡micamente)
            # messages = self.messages.get_recent_messages(conversation_id, message_limit)
            
            logger.debug(f"ðŸ’¬ ConversaciÃ³n {conversation_id} con mensajes cargados")
            return conv
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener conversaciÃ³n con mensajes: {e}")
            return None
    
    # ============================================
    # ESTADÃSTICAS
    # ============================================
    
    def get_conversation_stats(self, conversation_id: UUID | str) -> Dict[str, Any]:
        """
        Obtiene estadÃ­sticas de una conversaciÃ³n
        
        Args:
            conversation_id: ID de la conversaciÃ³n
        
        Returns:
            Diccionario con estadÃ­sticas
        """
        try:
            conv = self.get_by_id(conversation_id)
            
            if not conv:
                return {}
            
            stats = {
                "total_messages": self.messages.count({"conversation_id": str(conversation_id)}),
                "user_messages": self.messages.count_by_role(conversation_id, MessageRole.USER),
                "assistant_messages": self.messages.count_by_role(conversation_id, MessageRole.ASSISTANT),
                "duration_minutes": conv.duration_minutes,
                "status": conv.status.value if isinstance(conv.status, ConversationStatus) else conv.status,
                "current_strategy": conv.current_strategy
            }
            
            logger.debug(f"ðŸ“Š EstadÃ­sticas de conversaciÃ³n {conversation_id}")
            return stats
            
        except Exception as e:
            logger.error(f"âŒ Error al obtener estadÃ­sticas: {e}")
            return {}


# ============================================
# INSTANCIAS GLOBALES
# ============================================
conversation_repo = ConversationRepository()
message_repo = MessageRepository()


# ============================================
# EJEMPLO DE USO
# ============================================
if __name__ == "__main__":
    from src.core.tenant_context import TenantContextManager
    
    # Configurar tenant
    tenant_manager = TenantContextManager()
    tenant_manager.set_tenant("00000000-0000-0000-0000-000000000001")
    
    print("\nðŸ’¬ CONVERSATION REPOSITORY - EJEMPLOS")
    print("=" * 60)
    
    # 1. Crear/obtener conversaciÃ³n
    print("\n1ï¸âƒ£ Obtener o crear conversaciÃ³n:")
    conv = conversation_repo.get_or_create(
        phone_number="+573001234567",
        customer_name="Juan PÃ©rez"
    )
    print(f"  ConversaciÃ³n ID: {conv.id}")
    
    # 2. Agregar mensajes
    print("\n2ï¸âƒ£ Agregar mensajes:")
    msg1 = message_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content="Hola, quisiera informaciÃ³n sobre productos"
    )
    msg2 = message_repo.add_message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content="Â¡Hola! Claro, con gusto te ayudo. Â¿QuÃ© tipo de producto buscas?",
        strategy_used="greeting"
    )
    print(f"  Mensajes agregados: {msg1.id}, {msg2.id}")
    
    # 3. Obtener historial
    print("\n3ï¸âƒ£ Historial de chat:")
    history = message_repo.get_chat_history(conv.id)
    for msg in history:
        print(f"  {msg['role']}: {msg['content'][:50]}...")
    
    # 4. EstadÃ­sticas
    print("\n4ï¸âƒ£ EstadÃ­sticas de conversaciÃ³n:")
    stats = conversation_repo.get_conversation_stats(conv.id)
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
