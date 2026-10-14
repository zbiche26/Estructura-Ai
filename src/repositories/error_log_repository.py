from typing import List, Dict, Any
from datetime import datetime, timedelta

from src.repositories.base import BaseRepository
from src.core.database import db
from src.core.logger import logger
from src.core.tenant_context import TenantContextManager


class ErrorLogRepository(BaseRepository[Dict[str, Any]]):
    """Repository para leer logs de errores recientes."""

    def __init__(self, client=None):
        super().__init__(
            table_name="error_logs",
            model_class=dict,
            client=client or db.client,
        )

    def get_recent_errors(self, tenant_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtiene errores recientes filtrados por tenant (obligatorio)."""
        safe_limit = max(1, min(limit, 100))
        try:
            query = (
                self.client.table(self.table_name)
                .select("id, message, level, created_at, metadata")
                .eq("tenant_id", tenant_id)
                .order("created_at", desc=True)
                .limit(safe_limit)
            )
            result = query.execute()
            return result.data or []
        except Exception as exc:
            logger.error(f"❌ Error al leer logs (tenant_id={tenant_id}): {exc}")
            return []
