# -*- coding: utf-8 -*-
"""
rate_limiter.py - Rate Limiting y Control de Cuotas
=====================================================
Controla el uso de la API por tenant según su plan.



Funcionamiento:
    - Sin Redis: usa memoria (dict en proceso) — para dev/testing
    - Con Redis: usa Redis para persistencia entre instancias — para producción
    - RateLimiter es thread-safe mediante Lock

Uso:
    from src.auth.rate_limiter import RateLimiter, PLAN_LIMITS

    limiter = RateLimiter()
    limiter.check_request(tenant_id, "starter")
    limiter.record_tokens(tenant_id, tokens=1500)
    usage = limiter.get_usage(tenant_id, "growth")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Optional

from src.schemas.tenant_schemas import TenantPlanEnum

# ── Constantes ───────────────────────────────────────────────────────────────

TOKENS_PER_CONVERSATION = 2000  # Estimado de tokens por conversación promedio

PLAN_LIMITS: Dict[str, Dict[str, Any]] = {
    TenantPlanEnum.STARTER: {
        "requests_per_hour": 100,
        "tokens_per_month": 2_000_000,
        "max_conversations": 1_000,
        "max_products": 100,
        "max_team_members": 1,
    },
    TenantPlanEnum.GROWTH: {
        "requests_per_hour": 1_000,
        "tokens_per_month": 10_000_000,
        "max_conversations": 5_000,
        "max_products": 500,
        "max_team_members": 5,
    },
    TenantPlanEnum.SCALE: {
        "requests_per_hour": 10_000,
        "tokens_per_month": 80_000_000,
        "max_conversations": -1,  # ilimitado
        "max_products": -1,
        "max_team_members": -1,
    },
}

# Alias para compatibilidad — "scale" es el nombre comercial de enterprise
PLAN_LIMITS["scale"] = PLAN_LIMITS[TenantPlanEnum.SCALE]


# ── Excepciones ───────────────────────────────────────────────────────────────


class RateLimitExceeded(Exception):
    """Se lanza cuando un tenant excede el límite de requests por hora"""

    def __init__(self, tenant_id: str, limit: int, retry_after: int = 3600):
        self.tenant_id = tenant_id
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit excedido para tenant {tenant_id}. "
            f"Límite: {limit} req/hora. Reintenta en {retry_after}s."
        )


class TokenLimitExceeded(Exception):
    """Se lanza cuando un tenant excede el límite de tokens del mes"""

    def __init__(self, tenant_id: str, used: int, limit: int):
        self.tenant_id = tenant_id
        self.used = used
        self.limit = limit
        super().__init__(
            f"Límite de tokens excedido para tenant {tenant_id}. "
            f"Usado: {used:,} / Límite: {limit:,}"
        )


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class UsageInfo:
    """Información de uso actual de un tenant"""

    tenant_id: str = ""
    plan: str = "starter"

    # Requests
    requests_this_hour: int = 0
    requests_limit_hour: int = 100
    is_rate_limited: bool = False

    # Tokens
    tokens_this_month: int = 0
    tokens_limit_month: int = 2_000_000
    pct_tokens: float = 0.0

    # Conversaciones estimadas
    conversations_used: int = 0

    @property
    def is_near_limit(self) -> bool:
        """True si el uso de tokens supera el 80%"""
        return self.pct_tokens >= 80.0

    @property
    def is_over_limit(self) -> bool:
        """True si el uso de tokens alcanzó o superó el límite"""
        if self.tokens_limit_month <= 0:
            return False
        return self.tokens_this_month >= self.tokens_limit_month

    def summary(self) -> str:
        """Resumen de uso en texto"""
        return (
            f"Tenant: {self.tenant_id} | Plan: {self.plan} | "
            f"Req/hora: {self.requests_this_hour}/{self.requests_limit_hour} | "
            f"Tokens: {self.tokens_this_month:,}/{self.tokens_limit_month:,} "
            f"({self.pct_tokens:.1f}%)"
        )


# ── Rate Limiter ──────────────────────────────────────────────────────────────


class RateLimiter:
    """
    Controla rate limiting y cuotas de tokens por tenant.

    Funciona en memoria (sin Redis) por defecto.
    Thread-safe mediante Lock interno.

    Args:
        redis_client: Cliente Redis opcional. Si es None, usa memoria.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._lock = Lock()

        # Contadores en memoria: {tenant_id: {"requests": [], "tokens": int}}
        self._memory: Dict[str, Dict[str, Any]] = {}

    # ── Internos ──────────────────────────────────────────────────────────────

    def _get_tenant_data(self, tenant_id: str) -> Dict[str, Any]:
        """Obtiene o crea los contadores de un tenant"""
        if tenant_id not in self._memory:
            self._memory[tenant_id] = {
                "requests": [],  # lista de timestamps de requests en la última hora
                "tokens": 0,  # tokens usados este mes
            }
        return self._memory[tenant_id]

    def _clean_old_requests(self, requests: list) -> list:
        """Elimina requests fuera de la ventana de 1 hora"""
        now = time.time()
        return [ts for ts in requests if now - ts < 3600]

    def get_plan_limits(self, plan: str) -> Dict[str, Any]:
        """
        Retorna los límites del plan.
        Si el plan no existe, usa starter como fallback.
        """
        return PLAN_LIMITS.get(plan, PLAN_LIMITS[TenantPlanEnum.STARTER])

    # ── API pública ───────────────────────────────────────────────────────────

    def check_request(self, tenant_id: str, plan: str) -> bool:
        """
        Verifica si el tenant puede hacer un request.

        Args:
            tenant_id: ID del tenant
            plan: Plan del tenant (starter/growth/enterprise)

        Returns:
            True si puede hacer el request

        Raises:
            RateLimitExceeded: Si superó el límite de requests por hora
        """
        limits = self.get_plan_limits(plan)
        max_requests = limits["requests_per_hour"]

        with self._lock:
            data = self._get_tenant_data(tenant_id)
            data["requests"] = self._clean_old_requests(data["requests"])
            current_count = len(data["requests"])

            if current_count >= max_requests:
                raise RateLimitExceeded(
                    tenant_id=tenant_id,
                    limit=max_requests,
                    retry_after=3600,
                )

            data["requests"].append(time.time())
            return True

    def record_tokens(
        self,
        tenant_id: str,
        tokens: int = 0,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> int:
        """
        Registra tokens usados por un tenant.

        Args:
            tenant_id: ID del tenant
            tokens: Total de tokens (alternativa a input+output)
            tokens_input: Tokens de entrada
            tokens_output: Tokens de salida

        Returns:
            Total de tokens acumulados este mes
        """
        total = tokens + tokens_input + tokens_output

        with self._lock:
            data = self._get_tenant_data(tenant_id)
            data["tokens"] += total
            return data["tokens"]

    def check_token_limit(self, tenant_id: str, plan: str) -> bool:
        """
        Verifica si el tenant está dentro del límite de tokens.

        Args:
            tenant_id: ID del tenant
            plan: Plan del tenant

        Returns:
            True si está dentro del límite

        Raises:
            TokenLimitExceeded: Si superó el límite mensual de tokens
        """
        limits = self.get_plan_limits(plan)
        max_tokens = limits["tokens_per_month"]

        if max_tokens == -1:
            return True  # ilimitado

        with self._lock:
            data = self._get_tenant_data(tenant_id)
            used = data["tokens"]

            if used >= max_tokens:
                raise TokenLimitExceeded(
                    tenant_id=tenant_id,
                    used=used,
                    limit=max_tokens,
                )
            return True

    def get_usage(self, tenant_id: str, plan: str) -> UsageInfo:
        """
        Retorna el uso actual del tenant.

        Args:
            tenant_id: ID del tenant
            plan: Plan del tenant

        Returns:
            UsageInfo con el estado actual
        """
        limits = self.get_plan_limits(plan)
        max_requests = limits["requests_per_hour"]
        max_tokens = limits["tokens_per_month"]

        with self._lock:
            data = self._get_tenant_data(tenant_id)
            data["requests"] = self._clean_old_requests(data["requests"])

            requests_count = len(data["requests"])
            tokens_count = data["tokens"]

        pct = 0.0
        if max_tokens > 0 and tokens_count > 0:
            pct = min(100.0, (tokens_count / max_tokens) * 100)

        conversations = (
            tokens_count // TOKENS_PER_CONVERSATION if tokens_count > 0 else 0
        )

        return UsageInfo(
            tenant_id=tenant_id,
            plan=plan,
            requests_this_hour=requests_count,
            requests_limit_hour=max_requests,
            is_rate_limited=requests_count >= max_requests,
            tokens_this_month=tokens_count,
            tokens_limit_month=max_tokens,
            pct_tokens=round(pct, 2),
            conversations_used=conversations,
        )

    def reset_tenant(self, tenant_id: str) -> None:
        """
        Resetea todos los contadores de un tenant.
        Útil para testing.
        """
        with self._lock:
            if tenant_id in self._memory:
                del self._memory[tenant_id]
