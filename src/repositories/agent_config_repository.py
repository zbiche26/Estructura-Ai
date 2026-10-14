from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any

from src.repositories.base import BaseRepository
from src.models import AgentConfig
from src.core.database import db
from src.core.logger import logger


class AgentConfigRepository(BaseRepository[AgentConfig]):
    """Repository para la tabla agent_config."""

    def __init__(self, client=None):
        super().__init__(table_name="agent_config", model_class=AgentConfig, client=client or db.client)

    def get_by_tenant_id(self, tenant_id: str) -> Optional[AgentConfig]:
        if not tenant_id:
            raise ValueError("tenant_id is required")

        try:
            result = (
                self.client.table(self.table_name)
                .select("*")
                .eq("tenant_id", str(tenant_id))
                .limit(1)
                .execute()
            )

            if not result.data:
                logger.debug(f"⊘ Agent config no encontrada para tenant {tenant_id}")
                return None

            return AgentConfig(**result.data[0])
        except Exception as e:
            logger.error(f"❌ Error obteniendo agent_config para tenant {tenant_id}: {e}")
            raise

    def update_for_tenant(self, tenant_id: str, data: Dict[str, Any]) -> Optional[AgentConfig]:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if "tenant_id" in data:
            raise ValueError("tenant_id cannot be modified")

        try:
            payload = dict(data)
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()

            result = (
                self.client.table(self.table_name)
                .update(payload)
                .eq("tenant_id", str(tenant_id))
                .execute()
            )

            if not result.data or len(result.data) == 0:
                logger.warning(f"⚠️ No se encontró agent_config para actualizar: {tenant_id}")
                return None

            return AgentConfig(**result.data[0])
        except Exception as e:
            logger.error(f"❌ Error actualizando agent_config para tenant {tenant_id}: {e}")
            raise

    def upsert_for_tenant(self, tenant_id: str, data: Dict[str, Any]) -> AgentConfig:
        if not tenant_id:
            raise ValueError("tenant_id is required")

        try:
            data = dict(data)
            data["tenant_id"] = str(tenant_id)
            data["updated_at"] = datetime.now(timezone.utc).isoformat()

            existing = self.get_by_tenant_id(tenant_id)
            if existing:
                result = (
                    self.client.table(self.table_name)
                    .update(data)
                    .eq("tenant_id", str(tenant_id))
                    .execute()
                )
            else:
                result = self.client.table(self.table_name).insert(data).execute()

            if not result.data or len(result.data) == 0:
                raise Exception("No se pudo guardar agent_config")

            return AgentConfig(**result.data[0])
        except Exception as e:
            logger.error(f"❌ Error guardando agent_config para tenant {tenant_id}: {e}")
            raise
