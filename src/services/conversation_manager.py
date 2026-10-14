"""
Conversation Manager - Gestiona múltiples conversaciones simultáneas

Este módulo maneja:
- Creación de conversaciones
- Almacenamiento y recuperación
- Gestión de sesiones activas
- Limpieza de conversaciones antiguas
"""
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import json

from src.models.conversation import (
    Conversation,
    ConversationMetadata,
    ConversationStatus,
    Message,
    create_system_message
)
from src.core.logger import logger
from src.core.tenant_context import TenantContextManager


class ConversationManager:
    """
    Gestiona múltiples conversaciones simultáneas
    
    Mantiene conversaciones en memoria y opcionalmente las persiste
    en una base de datos.
    """
    
    def __init__(
        self,
        repository = None,
        max_active_conversations: int = 100,
        conversation_timeout_hours: int = 24
    ):
        """
        Inicializa el Conversation Manager
        
        Args:
            repository: Repositorio para persistir conversaciones (opcional)
            max_active_conversations: Máximo de conversaciones en memoria
            conversation_timeout_hours: Horas antes de considerar inactiva
        """
        self.repository = repository
        self.max_active_conversations = max_active_conversations
        self.conversation_timeout = timedelta(hours=conversation_timeout_hours)
        
        # Almacenamiento en memoria: {conversation_id: Conversation}
        self._conversations: Dict[str, Conversation] = {}
        
        # Índice por tenant: {tenant_id: [conversation_ids]}
        self._tenant_index: Dict[str, List[str]] = {}
        
        # Índice por usuario: {user_id: conversation_id}
        self._user_index: Dict[str, str] = {}
        
        logger.info(
            f"ConversationManager inicializado: "
            f"max={max_active_conversations}, timeout={conversation_timeout_hours}h"
        )
    
    def create_conversation(
        self,
        tenant_id: str,
        platform: str = "whatsapp",
        user_phone: Optional[str] = None,
        user_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Conversation:
        """
        Crea una nueva conversación
        
        Args:
            tenant_id: ID del tenant
            platform: Plataforma de origen (whatsapp, telegram, web)
            user_phone: Teléfono del usuario
            user_name: Nombre del usuario
            system_prompt: Prompt del sistema (opcional)
            context: Contexto adicional (opcional)
            
        Returns:
            Nueva conversación creada
        """
        # Crear metadata
        metadata = ConversationMetadata(
            platform=platform,
            user_phone=user_phone,
            user_name=user_name
        )
        
        # Crear conversación
        conversation = Conversation(
            tenant_id=tenant_id,
            metadata=metadata,
            context=context or {}
        )
        
        # Generar ID si no existe
        if not conversation.id:
            conversation.id = self._generate_conversation_id(
                tenant_id, user_phone or "unknown"
            )
        
        # Agregar mensaje del sistema si hay prompt
        if system_prompt:
            system_msg = create_system_message(system_prompt)
            conversation.add_message(system_msg)
        
        # Guardar en memoria
        self._conversations[conversation.id] = conversation
        
        # Actualizar índices
        self._add_to_tenant_index(tenant_id, conversation.id)
        if user_phone:
            self._user_index[user_phone] = conversation.id
        
        logger.info(
            f"Conversación creada: {conversation.id} "
            f"(tenant={tenant_id}, user={user_name or 'unknown'})"
        )
        
        # Guardar en DB si hay repositorio
        if self.repository:
            self._save_to_repository(conversation)
        
        return conversation
    
    def get_conversation(
        self,
        conversation_id: str,
        load_from_db: bool = True
    ) -> Optional[Conversation]:
        """
        Obtiene una conversación por ID
        
        Args:
            conversation_id: ID de la conversación
            load_from_db: Si cargar desde DB si no está en memoria
            
        Returns:
            Conversación o None si no existe
        """
        # Buscar en memoria
        conversation = self._conversations.get(conversation_id)
        
        # Si no está y hay DB, intentar cargar
        if not conversation and load_from_db and self.repository:
            conversation = self._load_from_repository(conversation_id)
            if conversation:
                self._conversations[conversation_id] = conversation
        
        return conversation
    
    def get_or_create_conversation(
        self,
        tenant_id: str,
        user_id: str,
        **kwargs
    ) -> Conversation:
        """
        Obtiene conversación existente o crea una nueva
        
        Args:
            tenant_id: ID del tenant
            user_id: ID del usuario (teléfono)
            **kwargs: Argumentos adicionales para create_conversation
            
        Returns:
            Conversación existente o nueva
        """
        # Buscar conversación activa del usuario
        conversation_id = self._user_index.get(user_id)
        
        if conversation_id:
            conversation = self.get_conversation(conversation_id)
            
            # Verificar que no esté expirada
            if conversation and not self._is_expired(conversation):
                return conversation
        
        # Crear nueva conversación
        return self.create_conversation(
            tenant_id=tenant_id,
            user_phone=user_id,
            **kwargs
        )
    
    def save_conversation(self, conversation: Conversation) -> bool:
        """
        Guarda una conversación
        
        Args:
            conversation: Conversación a guardar
            
        Returns:
            True si se guardó exitosamente
        """
        if not conversation.id:
            logger.error("No se puede guardar conversación sin ID")
            return False
        
        # Actualizar en memoria
        self._conversations[conversation.id] = conversation
        
        # Guardar en DB si hay repositorio
        if self.repository:
            return self._save_to_repository(conversation)
        
        return True
    
    def close_conversation(self, conversation_id: str) -> bool:
        """
        Cierra una conversación
        
        Args:
            conversation_id: ID de la conversación
            
        Returns:
            True si se cerró exitosamente
        """
        conversation = self.get_conversation(conversation_id)
        
        if not conversation:
            logger.warning(f"Conversación {conversation_id} no encontrada")
            return False
        
        conversation.close()
        self.save_conversation(conversation)
        
        logger.info(f"Conversación cerrada: {conversation_id}")
        return True
    
    def list_conversations(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[ConversationStatus] = None,
        limit: int = 50
    ) -> List[Conversation]:
        """
        Lista conversaciones
        
        Args:
            tenant_id: Filtrar por tenant (opcional)
            status: Filtrar por estado (opcional)
            limit: Número máximo de resultados
            
        Returns:
            Lista de conversaciones
        """
        conversations = list(self._conversations.values())
        
        # Filtrar por tenant
        if tenant_id:
            conversations = [
                c for c in conversations
                if c.tenant_id == tenant_id
            ]
        
        # Filtrar por estado
        if status:
            conversations = [
                c for c in conversations
                if c.status == status
            ]
        
        # Ordenar por más recientes
        conversations.sort(
            key=lambda c: c.updated_at,
            reverse=True
        )
        
        return conversations[:limit]
    
    def get_active_conversations(self, tenant_id: str) -> List[Conversation]:
        """
        Obtiene conversaciones activas de un tenant
        
        Args:
            tenant_id: ID del tenant
            
        Returns:
            Lista de conversaciones activas
        """
        return self.list_conversations(
            tenant_id=tenant_id,
            status=ConversationStatus.ACTIVE
        )
    
    def cleanup_expired_conversations(self) -> int:
        """
        Limpia conversaciones expiradas
        
        Returns:
            Número de conversaciones limpiadas
        """
        now = datetime.now(timezone.utc)
        expired_ids = []
        
        for conv_id, conversation in self._conversations.items():
            if self._is_expired(conversation):
                expired_ids.append(conv_id)
                
                # Archivar antes de eliminar
                conversation.archive()
                if self.repository:
                    self._save_to_repository(conversation)
        
        # Eliminar de memoria
        for conv_id in expired_ids:
            self._remove_from_memory(conv_id)
        
        if expired_ids:
            logger.info(f"Limpiadas {len(expired_ids)} conversaciones expiradas")
        
        return len(expired_ids)
    
    def get_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene estadísticas de conversaciones
        
        Args:
            tenant_id: Filtrar por tenant (opcional)
            
        Returns:
            Diccionario con estadísticas
        """
        conversations = self.list_conversations(tenant_id=tenant_id, limit=1000)
        
        stats = {
            "total": len(conversations),
            "active": len([c for c in conversations if c.status == ConversationStatus.ACTIVE]),
            "closed": len([c for c in conversations if c.status == ConversationStatus.CLOSED]),
            "archived": len([c for c in conversations if c.status == ConversationStatus.ARCHIVED]),
            "total_messages": sum(len(c.messages) for c in conversations),
            "total_tokens": sum(c.total_tokens for c in conversations),
        }
        
        if conversations:
            stats["avg_messages_per_conversation"] = stats["total_messages"] / stats["total"]
            stats["avg_tokens_per_conversation"] = stats["total_tokens"] / stats["total"]
        
        return stats
    
    # ==================== MÉTODOS PRIVADOS ====================
    
    def _generate_conversation_id(self, tenant_id: str, user_id: str) -> str:
        """Genera ID único para conversación"""
        import uuid
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        unique = str(uuid.uuid4())[:8]
        return f"conv_{tenant_id}_{user_id}_{timestamp}_{unique}"
    
    def _is_expired(self, conversation: Conversation) -> bool:
        """Verifica si una conversación está expirada"""
        if conversation.status in [ConversationStatus.CLOSED, ConversationStatus.ARCHIVED]:
            return False
        
        now = datetime.now(timezone.utc)
        time_since_update = now - conversation.updated_at
        return time_since_update > self.conversation_timeout
    
    def _add_to_tenant_index(self, tenant_id: str, conversation_id: str):
        """Agrega conversación al índice de tenant"""
        if tenant_id not in self._tenant_index:
            self._tenant_index[tenant_id] = []
        self._tenant_index[tenant_id].append(conversation_id)
    
    def _remove_from_memory(self, conversation_id: str):
        """Elimina conversación de memoria e índices"""
        conversation = self._conversations.pop(conversation_id, None)
        
        if conversation:
            # Eliminar de índice de tenant
            tenant_id = conversation.tenant_id
            if tenant_id in self._tenant_index:
                self._tenant_index[tenant_id] = [
                    cid for cid in self._tenant_index[tenant_id]
                    if cid != conversation_id
                ]
            
            # Eliminar de índice de usuario
            user_phone = conversation.metadata.user_phone
            if user_phone and self._user_index.get(user_phone) == conversation_id:
                del self._user_index[user_phone]
    
    def _save_to_repository(self, conversation: Conversation) -> bool:
        """Guarda conversación en repositorio"""
        try:
            # Convertir a dict
            data = conversation.to_dict()
            
            # Guardar en repositorio (implementación depende del repo)
            # Por ahora solo log
            logger.debug(f"Guardando conversación {conversation.id} en repositorio")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando conversación: {e}")
            return False
    
    def _load_from_repository(self, conversation_id: str) -> Optional[Conversation]:
        """Carga conversación desde repositorio"""
        try:
            # Cargar desde repositorio (implementación depende del repo)
            # Por ahora retorna None
            logger.debug(f"Intentando cargar conversación {conversation_id} desde repositorio")
            return None
            
        except Exception as e:
            logger.error(f"Error cargando conversación: {e}")
            return None