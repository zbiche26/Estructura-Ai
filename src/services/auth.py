from __future__ import annotations

import os
from typing import Optional
from src.core.logger import logger
from src.services.tenant_service import load_tenant_context  # Re-exportar


def parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]

    return authorization

