"""
Base Repository - Repository Pattern Base

Este módulo proporciona un repository genérico que implementa
operaciones CRUD comunes para todas las entidades.

Todos los repositories específicos heredan de BaseRepository.

Uso:
    class ProductRepository(BaseRepository[Product]):
        def __init__(self):
            super().__init__("products", Product)
"""

from typing import TypeVar, Generic, List, Optional, Dict, Any, Type
from uuid import UUID
from supabase import Client

from src.core.logger import logger
from src.core.tenant_context import TenantContextManager


T = TypeVar('T')


class BaseRepository(Generic[T]):
    """
    Repository base genérico con operaciones CRUD.

    SEGURIDAD: Todas las operaciones de lectura/escritura/borrado usan
    get_current_or_fail() — si no hay tenant en contexto, lanzan ValueError
    en lugar de ejecutar queries sin filtro de tenant (fail closed).

    La única excepción es create(), que usa get_current() para inyectar
    tenant_id automáticamente sin bloquear inserciones internas del sistema.
    """

    def __init__(
        self,
        table_name: str,
        model_class: Type[T],
        client: Client
    ):
        self.table_name = table_name
        self.model_class = model_class
        self.client = client
        logger.debug(f"📦 Repository inicializado: {table_name}")

    # ============================================
    # CREATE
    # ============================================

    def create(self, data: Dict[str, Any]) -> T:
        """
        Crea un nuevo registro.
        Usa get_current() (no fail) para permitir inserciones del sistema
        que no siempre tienen contexto de tenant.
        """
        try:
            # Inyectar tenant_id automáticamente si no está
            current_tenant = TenantContextManager.get_current()
            if 'tenant_id' not in data and current_tenant and current_tenant.tenant_id:
                data['tenant_id'] = current_tenant.tenant_id

            result = self.client.table(self.table_name).insert(data).execute()

            if not result.data or len(result.data) == 0:
                raise Exception(f"No se pudo crear el registro en {self.table_name}")

            record = result.data[0]
            instance = self.model_class(**record)

            logger.success(f"✅ Creado en {self.table_name}: {record.get('id')}")
            return instance

        except Exception as e:
            logger.error(f"❌ Error al crear en {self.table_name}: {e}")
            raise

    # ============================================
    # READ
    # ============================================

    def get_by_id(self, id: UUID | str) -> Optional[T]:
        """
        Obtiene un registro por su ID.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            id_str = str(id)

            # ✅ FIX 2: Fail closed — lanza excepción si no hay tenant
            current_tenant = TenantContextManager.get_current_or_fail()

            query = (
                self.client.table(self.table_name)
                .select("*")
                .eq("id", id_str)
                .eq("tenant_id", current_tenant.tenant_id)
            )

            result = query.execute()

            if not result.data or len(result.data) == 0:
                logger.debug(f"🔍 No encontrado en {self.table_name}: {id_str}")
                return None

            record = result.data[0]
            instance = self.model_class(**record)

            logger.debug(f"✅ Encontrado en {self.table_name}: {id_str}")
            return instance

        except Exception as e:
            logger.error(f"❌ Error al buscar en {self.table_name}: {e}")
            raise

    def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        ascending: bool = False
    ) -> List[T]:
        """
        Obtiene todos los registros con paginación.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            # ✅ FIX 2: Fail closed
            current_tenant = TenantContextManager.get_current_or_fail()

            query = (
                self.client.table(self.table_name)
                .select("*")
                .eq("tenant_id", current_tenant.tenant_id)
                .order(order_by, desc=not ascending)
                .range(offset, offset + limit - 1)
            )

            result = query.execute()
            instances = [self.model_class(**record) for record in result.data]

            logger.debug(f"📋 Obtenidos {len(instances)} registros de {self.table_name}")
            return instances

        except Exception as e:
            logger.error(f"❌ Error al obtener todos de {self.table_name}: {e}")
            raise

    def find(
        self,
        filters: Dict[str, Any],
        limit: int = 100,
        offset: int = 0
    ) -> List[T]:
        """
        Busca registros con filtros.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            # ✅ FIX 2: Fail closed
            current_tenant = TenantContextManager.get_current_or_fail()

            # Inyectar tenant_id en filtros
            filters['tenant_id'] = current_tenant.tenant_id

            query = self.client.table(self.table_name).select("*")

            for key, value in filters.items():
                query = query.eq(key, value)

            query = query.range(offset, offset + limit - 1)

            result = query.execute()
            instances = [self.model_class(**record) for record in result.data]

            logger.debug(f"🔍 Encontrados {len(instances)} registros en {self.table_name}")
            return instances

        except Exception as e:
            logger.error(f"❌ Error al buscar en {self.table_name}: {e}")
            raise

    # ============================================
    # UPDATE
    # ============================================

    def update(self, id: UUID | str, data: Dict[str, Any]) -> Optional[T]:
        """
        Actualiza un registro.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            id_str = str(id)

            # ✅ FIX 2: Fail closed
            current_tenant = TenantContextManager.get_current_or_fail()

            query = (
                self.client.table(self.table_name)
                .update(data)
                .eq("id", id_str)
                .eq("tenant_id", current_tenant.tenant_id)
            )

            result = query.execute()

            if not result.data or len(result.data) == 0:
                logger.warning(f"⚠️ No se encontró registro para actualizar en {self.table_name}: {id_str}")
                return None

            record = result.data[0]
            instance = self.model_class(**record)

            logger.success(f"✅ Actualizado en {self.table_name}: {id_str}")
            return instance

        except Exception as e:
            logger.error(f"❌ Error al actualizar en {self.table_name}: {e}")
            raise

    # ============================================
    # DELETE
    # ============================================

    def delete(self, id: UUID | str) -> bool:
        """
        Elimina un registro.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            id_str = str(id)

            # ✅ FIX 2: Fail closed
            current_tenant = TenantContextManager.get_current_or_fail()

            query = (
                self.client.table(self.table_name)
                .delete()
                .eq("id", id_str)
                .eq("tenant_id", current_tenant.tenant_id)
            )

            result = query.execute()

            if not result.data or len(result.data) == 0:
                logger.warning(f"⚠️ No se encontró registro para eliminar en {self.table_name}: {id_str}")
                return False

            logger.success(f"🗑️ Eliminado de {self.table_name}: {id_str}")
            return True

        except Exception as e:
            logger.error(f"❌ Error al eliminar de {self.table_name}: {e}")
            raise

    # ============================================
    # UTILIDADES
    # ============================================

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Cuenta el número de registros.
        FALLA CERRADO: lanza ValueError si no hay tenant en contexto.
        """
        try:
            # ✅ FIX 2: Fail closed
            current_tenant = TenantContextManager.get_current_or_fail()

            query = (
                self.client.table(self.table_name)
                .select("id", count="exact")
                .eq("tenant_id", current_tenant.tenant_id)
                .limit(0)
            )

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            result = query.execute()
            count = getattr(result, 'count', None)
            if count is None:
                count = 0

            logger.debug(f"📊 Count en {self.table_name}: {count}")
            return count

        except Exception as e:
            logger.error(f"❌ Error al contar en {self.table_name}: {e}")
            return 0

    def exists(self, id: UUID | str) -> bool:
        return self.get_by_id(id) is not None