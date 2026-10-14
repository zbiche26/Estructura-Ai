"""
Tenant Repository - Gestión de Tenants

Repository específico para la entidad Tenant con métodos
adicionales para búsqueda y validación de unicidad.

Uso:
    from src.repositories.tenant_repository import tenant_repo
    
    # Buscar tenant por email
    tenant = tenant_repo.find_by_email("admin@empresa.com")
    
    # Buscar tenant por slug
    tenant = tenant_repo.find_by_slug("mi-empresa")
    
    # Verificar si email ya existe
    exists = tenant_repo.check_email_exists("admin@empresa.com")
"""

from typing import Optional
from uuid import UUID

from src.repositories.base import BaseRepository
from src.models import Tenant
from src.core.logger import logger
from src.core.database import db


class TenantRepository(BaseRepository[Tenant]):
    def check_whatsapp_phone_exists(self, whatsapp_phone_number: str) -> bool:
        """
        Verifica si un número de WhatsApp ya existe en el sistema
        Útil para validar antes de crear un nuevo tenant.
        Args:
            whatsapp_phone_number: Número a verificar
        Returns:
            True si ya existe, False si no
        Raises:
            Exception: Si hay error en la BD
        """
        if not whatsapp_phone_number:
            return False
        try:
            result = (
                self.client.table(self.table_name)
                .select("id", count="exact")
                .eq("whatsapp_phone_number", whatsapp_phone_number)
                .execute()
            )
            count = result.count if hasattr(result, 'count') else len(result.data)
            exists = count > 0
            if exists:
                logger.warning(f"⚠️  WhatsApp phone ya existe en el sistema: {whatsapp_phone_number}")
            return exists
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de WhatsApp phone {whatsapp_phone_number}: {e}")
            raise

    def __init__(self, client=None):
        """Inicializa el repository de tenants."""
        from src.core.database import db
        super().__init__(
            table_name="tenants",
            model_class=Tenant,
            client=client or db.client
        )

    def check_whatsapp_phone_id_exists(self, whatsapp_phone_id: str) -> bool:
        """
        Verifica si un WhatsApp Phone ID ya existe en el sistema
        Útil para validar antes de crear un nuevo tenant.

        Args:
            whatsapp_phone_id: Phone ID de Meta a verificar

        Returns:
            True si ya existe, False si no

        Raises:
            Exception: Si hay error en la BD
        """
        if not whatsapp_phone_id:
            return False
        try:
            result = (
                self.client.table(self.table_name)
                .select("id", count="exact")
                .eq("whatsapp_phone_id", whatsapp_phone_id)
                .execute()
            )
            count = result.count if hasattr(result, 'count') else len(result.data)
            exists = count > 0
            if exists:
                logger.warning(f"⚠️  WhatsApp Phone ID ya existe en el sistema: {whatsapp_phone_id}")
            return exists
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de WhatsApp Phone ID {whatsapp_phone_id}: {e}")
            raise

    # ============================================
    # BÚSQUEDAS ESPECÍFICAS
    # ============================================

    def find_by_email(self, email: str) -> Optional[Tenant]:
        """
        Busca un tenant por su email
        
        El email debe ser único en la BD.
        
        Args:
            email: Email del administrador del tenant
        
        Returns:
            Tenant encontrado o None
            
        Raises:
            Exception: Si hay error en la BD
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("email", email.lower())
                .execute()
            )
            
            if result.data:
                tenant_data = result.data[0]
                logger.debug(f"✓ Tenant encontrado por email: {email}")
                return Tenant(**tenant_data)
            
            logger.debug(f"⊘ Tenant no encontrado por email: {email}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error al buscar tenant por email {email}: {e}")
            raise

    def find_by_id(self, tenant_id: UUID | str) -> Optional[Tenant]:
        """Busca un tenant por su ID."""
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("id", str(tenant_id))
                .execute()
            )

            if result.data:
                tenant_data = result.data[0]
                logger.debug(f"✓ Tenant encontrado por id: {tenant_id}")
                return Tenant(**tenant_data)

            logger.debug(f"⊘ Tenant no encontrado por id: {tenant_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error al buscar tenant por id {tenant_id}: {e}")
            raise
    
    def find_by_slug(self, slug: str) -> Optional[Tenant]:
        """
        Busca un tenant por su slug
        
        El slug debe ser único en la BD.
        
        Args:
            slug: Slug del tenant (identificador único)
        
        Returns:
            Tenant encontrado o None
            
        Raises:
            Exception: Si hay error en la BD
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("slug", slug.lower())
                .execute()
            )
            
            if result.data:
                tenant_data = result.data[0]
                logger.debug(f"✓ Tenant encontrado por slug: {slug}")
                return Tenant(**tenant_data)
            
            logger.debug(f"⊘ Tenant no encontrado por slug: {slug}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error al buscar tenant por slug {slug}: {e}")
            raise
    
    # ============================================
    # VALIDACIONES DE UNICIDAD
    # ============================================
    
    def check_email_exists(self, email: str) -> bool:
        """
        Verifica si un email ya existe en el sistema
        
        Útil para validar antes de crear un nuevo tenant.
        
        Args:
            email: Email a verificar
        
        Returns:
            True si el email ya existe, False si no
            
        Raises:
            Exception: Si hay error en la BD
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("id", count="exact")
                .eq("email", email.lower())
                .execute()
            )
            
            count = result.count if hasattr(result, 'count') else len(result.data)
            exists = count > 0
            
            if exists:
                logger.warning(f"⚠️  Email ya existe en el sistema: {email}")
            
            return exists
            
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de email {email}: {e}")
            raise
    
    def check_slug_exists(self, slug: str) -> bool:
        """
        Verifica si un slug ya existe en el sistema
        
        Útil para validar antes de crear un nuevo tenant.
        
        Args:
            slug: Slug a verificar
        
        Returns:
            True si el slug ya existe, False si no
            
        Raises:
            Exception: Si hay error en la BD
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("id", count="exact")
                .eq("slug", slug.lower())
                .execute()
            )
            
            count = result.count if hasattr(result, 'count') else len(result.data)
            exists = count > 0
            
            if exists:
                logger.warning(f"⚠️  Slug ya existe en el sistema: {slug}")
            
            return exists
            
        except Exception as e:
            logger.error(f"❌ Error al verificar existencia de slug {slug}: {e}")
            raise
    
    # ============================================
    # OPERACIONES ADICIONALES
    # ============================================

    def update(self, tenant_id: UUID | str, data: dict) -> Optional[Tenant]:
        try:
            result = (
                self.client.table(self.table_name)
                .update(data)
                .eq("id", str(tenant_id))
                .execute()
            )

            if not result.data:
                logger.warning(f"⚠️ No se encontró tenant para actualizar: {tenant_id}")
                return None

            tenant_data = result.data[0]
            logger.success(f"✅ Tenant actualizado: {tenant_id}")
            return Tenant(**tenant_data)

        except Exception as e:
            logger.error(f"❌ Error al actualizar tenant {tenant_id}: {e}")
            raise
    
    def get_active_tenants(self, limit: int = 100) -> list:
        """
        Obtiene solo los tenants activos
        
        Args:
            limit: Número máximo de resultados
        
        Returns:
            Lista de tenants activos
        """
        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("is_active", True)
                .limit(limit)
                .execute()
            )
            
            tenants = [Tenant(**record) for record in result.data]
            logger.debug(f"✓ {len(tenants)} tenants activos encontrados")
            return tenants
            
        except Exception as e:
            logger.error(f"❌ Error al obtener tenants activos: {e}")
            raise
    
    def deactivate_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """
        Desactiva un tenant
        
        Args:
            tenant_id: ID del tenant a desactivar
        
        Returns:
            Tenant desactivado o None
        """
        try:
            result = (
                self.client.table(self.table_name)
                .update({"is_active": False})
                .eq("id", str(tenant_id))
                .execute()
            )
            
            if result.data:
                tenant_data = result.data[0]
                logger.info(f"✓ Tenant desactivado: {tenant_id}")
                return Tenant(**tenant_data)
            
            logger.warning(f"⊘ No se pudo desactivar el tenant: {tenant_id}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error al desactivar tenant {tenant_id}: {e}")
            raise


# Instancia global del repository
tenant_repo = TenantRepository()
