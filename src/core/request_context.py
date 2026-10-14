from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    token: Optional[str] = None
    user_id: Optional[str] = None  # futuro: auth real
