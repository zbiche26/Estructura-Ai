"""
Billing Service - Sistema de facturación y cuotas

Este módulo contiene:
- PlanDefinitionService: Definición de límites por plan
- QuotaChecker: Verificación de límites en tiempo real
- UsageCalculator: Cálculo de uso actual vs límite
- BillingCalculator: Cálculo de costos mensuales y overages
- InvoiceGenerator: Generación de facturas
- UsageAlertManager: Gestión de alertas de uso
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.core.database import get_db, SupabaseClient
from src.core.logger import logger
from src.config import settings
from src.services.notification_service import NotificationService

# ✅ Fuente de verdad única para planes
from src.schemas.tenant_schemas import TenantPlanEnum


# ============================================
# Data Classes
# ============================================

@dataclass
class PlanLimits:
    """Límites de un plan"""

    messages_limit: int  # -1 = unlimited
    storage_limit_mb: float  # -1 = unlimited
    api_calls_limit: int  # -1 = unlimited
    products_limit: int  # -1 = unlimited
    conversations_limit: int  # -1 = unlimited
    users_limit: int  # -1 = unlimited
    vectors_limit: int  # -1 = unlimited

    # Precios
    monthly_price: float
    yearly_price: float

    # Rates de overage
    messages_overage_rate: float
    storage_overage_rate: float
    api_calls_overage_rate: float

    # Features
    features: List[str]


@dataclass
class Subscription:
    """Suscripción activa de un tenant"""

    id: str
    tenant_id: str
    plan_key: str
    status: str  # active, trialing, past_due, canceled, paused
    current_period_start: date
    current_period_end: date
    trial_end: Optional[date]
    billing_email: Optional[str]
    billing_cycle: str  # monthly, yearly
    allow_overages: bool


@dataclass
class QuotaCheckResult:
    """Resultado de verificación de cuota"""

    allowed: bool
    current_usage: float
    limit: float
    remaining: float
    percent_used: float
    overage_allowed: bool
    overage_rate: float


@dataclass
class ResourceUsage:
    """Uso de un recurso específico"""

    current: float
    limit: float
    percent: float
    remaining: float


@dataclass
class UsageSummary:
    """Resumen completo de uso"""

    period_start: date
    period_end: date
    messages: ResourceUsage
    storage: ResourceUsage
    api_calls: ResourceUsage
    products: ResourceUsage


@dataclass
class LineItem:
    """Línea de factura"""

    description: str
    quantity: float
    unit_price: float
    amount: float


@dataclass
class Invoice:
    """Factura"""

    id: Optional[str]
    invoice_number: str
    tenant_id: str
    period_start: date
    period_end: date
    line_items: List[LineItem]
    subtotal: float
    tax_amount: float
    total_amount: float
    status: str


# ============================================
# Plan Definition Service
# ============================================


class PlanDefinitionService:
    """
    Servicio de definiciones de planes.

    Fuente de verdad: TenantPlanEnum (starter, growth, enterprise).
    Provee los límites y precios de cada plan disponible.
    """

    _cache: Dict[str, PlanLimits] = {}

    @classmethod
    def get_plan_limits(cls, plan_key: str) -> PlanLimits:
        """
        Obtiene los límites de un plan.

        Args:
            plan_key: starter | growth | enterprise
        """
        # Normalizar — acepta valores legacy (free→starter, pro→growth)
        plan_key = cls._normalize_plan_key(plan_key)

        if plan_key in cls._cache:
            return cls._cache[plan_key]

        # Intentar cargar de BD
        try:
            db = get_db()
            result = (
                db.client.table("subscription_plans")
                .select(
                    "messages_limit, storage_limit_mb, api_calls_limit, "
                    "products_limit, conversations_limit, users_limit, vectors_limit, "
                    "monthly_price, yearly_price, "
                    "messages_overage_rate, storage_overage_rate, api_calls_overage_rate, "
                    "features"
                )
                .eq("plan_key", plan_key)
                .eq("is_active", True)
                .execute()
            )

            if result.data:
                plan = result.data[0]
                limits = PlanLimits(
                    messages_limit=plan["messages_limit"],
                    storage_limit_mb=float(plan["storage_limit_mb"] or 0),
                    api_calls_limit=plan["api_calls_limit"],
                    products_limit=plan["products_limit"],
                    conversations_limit=plan["conversations_limit"],
                    users_limit=plan["users_limit"],
                    vectors_limit=plan["vectors_limit"],
                    monthly_price=float(plan["monthly_price"] or 0),
                    yearly_price=float(plan["yearly_price"] or 0),
                    messages_overage_rate=float(plan["messages_overage_rate"] or 0),
                    storage_overage_rate=float(plan["storage_overage_rate"] or 0),
                    api_calls_overage_rate=float(plan["api_calls_overage_rate"] or 0),
                    features=plan["features"] or [],
                )
                cls._cache[plan_key] = limits
                return limits

        except Exception as e:
            logger.warning(f"Error cargando plan de BD, usando defaults: {e}")

        return cls._get_default_limits(plan_key)

    @classmethod
    def _normalize_plan_key(cls, plan_key: str) -> str:
        """
        Normaliza plan_key a los valores canónicos de TenantPlanEnum.
        Acepta valores legacy del billing_service anterior.
        """
        legacy_map = {
            "free": TenantPlanEnum.STARTER.value,
            "pro": TenantPlanEnum.GROWTH.value,
        }
        normalized = legacy_map.get(plan_key.lower(), plan_key.lower())
        valid = {e.value for e in TenantPlanEnum}
        if normalized not in valid:
            logger.warning(f"Plan key desconocido '{plan_key}', usando starter")
            return TenantPlanEnum.STARTER.value
        return normalized

    @classmethod
    def _get_default_limits(cls, plan_key: str) -> PlanLimits:
        """Límites por defecto — alineados con plans.py"""
        defaults = {
            TenantPlanEnum.STARTER.value: PlanLimits(
                messages_limit=1000,
                storage_limit_mb=500.0,
                api_calls_limit=5000,
                products_limit=100,
                conversations_limit=1000,
                users_limit=2,
                vectors_limit=5000,
                monthly_price=0,
                yearly_price=0,
                messages_overage_rate=0.01,
                storage_overage_rate=0.10,
                api_calls_overage_rate=0.001,
                features=["basic_analytics", "whatsapp_basic"],
            ),
            TenantPlanEnum.GROWTH.value: PlanLimits(
                messages_limit=5000,
                storage_limit_mb=2000.0,
                api_calls_limit=20000,
                products_limit=500,
                conversations_limit=5000,
                users_limit=5,
                vectors_limit=25000,
                monthly_price=29.99,
                yearly_price=299.99,
                messages_overage_rate=0.01,
                storage_overage_rate=0.10,
                api_calls_overage_rate=0.001,
                features=[
                    "basic_analytics",
                    "advanced_analytics",
                    "whatsapp_full",
                    "api_access",
                ],
            ),
            TenantPlanEnum.SCALE.value: PlanLimits(
                messages_limit=-1,
                storage_limit_mb=-1,
                api_calls_limit=-1,
                products_limit=-1,
                conversations_limit=-1,
                users_limit=-1,
                vectors_limit=-1,
                monthly_price=99.99,
                yearly_price=999.99,
                messages_overage_rate=0,
                storage_overage_rate=0,
                api_calls_overage_rate=0,
                features=[
                    "basic_analytics",
                    "advanced_analytics",
                    "whatsapp_full",
                    "api_access",
                    "enterprise",
                ],
            ),
        }
        return defaults.get(plan_key, defaults[TenantPlanEnum.STARTER.value])

    @classmethod
    def get_all_plans(cls, db: Optional[SupabaseClient] = None) -> List[Dict[str, Any]]:
        """Obtiene todos los planes disponibles desde la tabla `plans`."""
        db = db or get_db()
        plans: List[Dict[str, Any]] = []

        try:
            result = (
                db.client.table("plans")
                .select("slug, name, price_monthly, limits, features")
                .eq("is_active", True)
                .execute()
            )

            for row in result.data or []:
                raw_limits = row.get("limits")
                if isinstance(raw_limits, str):
                    try:
                        raw_limits = json.loads(raw_limits)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Limits del plan %s no son JSON válido: %s",
                            row.get("slug"),
                            raw_limits,
                        )
                        raw_limits = {}
                elif raw_limits is None:
                    raw_limits = {}

                raw_features = row.get("features")
                if isinstance(raw_features, str):
                    try:
                        raw_features = json.loads(raw_features)
                    except json.JSONDecodeError:
                        logger.warning(
                            "Features del plan %s no son JSON válido: %s",
                            row.get("slug"),
                            raw_features,
                        )
                        raw_features = []
                elif raw_features is None:
                    raw_features = []

                if not isinstance(raw_features, list):
                    raw_features = [str(raw_features)]

                plans.append(
                    {
                        "key": row.get("slug"),
                        "name": row.get("name"),
                        "limits": {
                            "agents": int(raw_limits.get("max_agents", 0)),
                            "users": int(raw_limits.get("max_team_members", 0)),
                            "conversations": int(raw_limits.get("max_conversations_month", 0)),
                            "messages": int(raw_limits.get("max_conversations_month", 0)),
                        },
                        "prices": {
                            "monthly": float(row.get("price_monthly", 0) or 0),
                        },
                        "features": raw_features,
                    }
                )

        except Exception as exc:
            logger.error("Error obteniendo planes desde la base de datos: %s", exc)
            raise

        return plans

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()


# ============================================
# Quota Checker
# ============================================


class QuotaChecker:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def check_quota(self, tenant_id: str, resource_type: str) -> QuotaCheckResult:
        subscription = self._get_subscription(tenant_id)
        if not subscription:
            return QuotaCheckResult(
                allowed=True,
                current_usage=0,
                limit=0,
                remaining=0,
                percent_used=0,
                overage_allowed=False,
                overage_rate=0,
            )

        plan_limits = PlanDefinitionService.get_plan_limits(subscription.plan_key)
        current_usage = self._get_current_usage(tenant_id, resource_type)
        limit = self._get_limit(plan_limits, resource_type)

        if limit == -1:
            return QuotaCheckResult(
                allowed=True,
                current_usage=current_usage,
                limit=-1,
                remaining=-1,
                percent_used=0,
                overage_allowed=False,
                overage_rate=0,
            )

        remaining = max(0, limit - current_usage)
        percent_used = (current_usage / limit) * 100 if limit > 0 else 0
        overage_allowed = subscription.allow_overages
        overage_rate = self._get_overage_rate(plan_limits, resource_type)
        allowed = remaining > 0 or overage_allowed

        return QuotaCheckResult(
            allowed=allowed,
            current_usage=current_usage,
            limit=limit,
            remaining=remaining,
            percent_used=round(percent_used, 2),
            overage_allowed=overage_allowed,
            overage_rate=overage_rate,
        )

    def check_all_quotas(self, tenant_id: str) -> Dict[str, QuotaCheckResult]:
        return {
            "messages": self.check_quota(tenant_id, "messages"),
            "storage": self.check_quota(tenant_id, "storage"),
            "api_calls": self.check_quota(tenant_id, "api_calls"),
            "products": self.check_quota(tenant_id, "products"),
        }

    def require_quota(self, tenant_id: str, resource_type: str, quantity: int = 1):
        result = self.check_quota(tenant_id, resource_type)
        if not result.allowed or result.remaining < quantity:
            raise QuotaExceededError(
                f"Cuota de {resource_type} excedida. "
                f"Usado: {result.current_usage}, Límite: {result.limit}"
            )

    def _get_subscription(self, tenant_id: str) -> Optional[Subscription]:
        try:
            result = (
                self.db.client.table("tenant_subscriptions")
                .select(
                    "id, tenant_id, plan_id, status, current_period_start, "
                    "current_period_end, trial_end, billing_email, billing_cycle, allow_overages"
                )
                .eq("tenant_id", tenant_id)
                .in_("status", ["active", "trialing"])
                .execute()
            )

            if not result.data:
                return None

            sub = result.data[0]
            plan_result = (
                self.db.client.table("subscription_plans")
                .select("plan_key")
                .eq("id", sub["plan_id"])
                .execute()
            )

            plan_key = (
                plan_result.data[0]["plan_key"]
                if plan_result.data
                else TenantPlanEnum.STARTER.value
            )

            return Subscription(
                id=sub["id"],
                tenant_id=sub["tenant_id"],
                plan_key=PlanDefinitionService._normalize_plan_key(plan_key),
                status=sub["status"],
                current_period_start=sub["current_period_start"],
                current_period_end=sub["current_period_end"],
                trial_end=sub.get("trial_end"),
                billing_email=sub.get("billing_email"),
                billing_cycle=sub.get("billing_cycle", "monthly"),
                allow_overages=sub.get("allow_overages", False),
            )

        except Exception as e:
            logger.warning(f"Error obteniendo suscripción: {e}")
            return None

    def _get_current_usage(self, tenant_id: str, resource_type: str) -> float:
        today = date.today()
        start_of_month = today.replace(day=1)
        try:
            result = (
                self.db.client.table("usage_records")
                .select("messages_count, storage_used_mb, api_calls_count")
                .eq("tenant_id", tenant_id)
                .gte("record_date", start_of_month.isoformat())
                .execute()
            )

            if not result.data:
                return 0

            total = 0
            for row in result.data:
                if resource_type == "messages":
                    total += row.get("messages_count", 0) or 0
                elif resource_type == "storage":
                    total += row.get("storage_used_mb", 0) or 0
                elif resource_type == "api_calls":
                    total += row.get("api_calls_count", 0) or 0
            return total

        except Exception as e:
            logger.warning(f"Error obteniendo uso actual: {e}")
            return 0

    def _get_limit(self, plan_limits: PlanLimits, resource_type: str) -> float:
        mapping = {
            "messages": plan_limits.messages_limit,
            "storage": plan_limits.storage_limit_mb,
            "api_calls": plan_limits.api_calls_limit,
            "products": plan_limits.products_limit,
        }
        return mapping.get(resource_type, 0)

    def _get_overage_rate(self, plan_limits: PlanLimits, resource_type: str) -> float:
        mapping = {
            "messages": plan_limits.messages_overage_rate,
            "storage": plan_limits.storage_overage_rate,
            "api_calls": plan_limits.api_calls_overage_rate,
        }
        return mapping.get(resource_type, 0)


class QuotaExceededError(Exception):
    pass


# ============================================
# Usage Calculator
# ============================================


class UsageCalculator:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def get_current_usage_summary(self, tenant_id: str) -> UsageSummary:
        subscription = self._get_subscription(tenant_id)
        if subscription:
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
            plan_key = subscription.plan_key
        else:
            today = date.today()
            period_start = today.replace(day=1)
            period_end = today
            plan_key = TenantPlanEnum.STARTER.value

        plan_limits = PlanDefinitionService.get_plan_limits(plan_key)
        usage = self._get_period_usage(tenant_id, period_start)

        return UsageSummary(
            period_start=period_start,
            period_end=period_end,
            messages=self._build_resource_usage(
                usage.get("messages", 0), plan_limits.messages_limit
            ),
            storage=self._build_resource_usage(
                float(usage.get("storage_mb", 0)), plan_limits.storage_limit_mb
            ),
            api_calls=self._build_resource_usage(
                usage.get("api_calls", 0), plan_limits.api_calls_limit
            ),
            products=self._build_resource_usage(
                usage.get("products", 0), plan_limits.products_limit
            ),
        )

    def _get_subscription(self, tenant_id: str) -> Optional[Subscription]:
        try:
            result = (
                self.db.client.table("tenant_subscriptions")
                .select("id, plan_id, current_period_start, current_period_end")
                .eq("tenant_id", tenant_id)
                .in_("status", ["active", "trialing"])
                .execute()
            )

            if not result.data:
                return None

            sub = result.data[0]
            plan_result = (
                self.db.client.table("subscription_plans")
                .select("plan_key")
                .eq("id", sub["plan_id"])
                .execute()
            )

            plan_key = (
                plan_result.data[0]["plan_key"]
                if plan_result.data
                else TenantPlanEnum.STARTER.value
            )

            return Subscription(
                id=sub["id"],
                tenant_id=tenant_id,
                plan_key=PlanDefinitionService._normalize_plan_key(plan_key),
                status="active",
                current_period_start=sub["current_period_start"],
                current_period_end=sub["current_period_end"],
                trial_end=None,
                billing_email=None,
                billing_cycle="monthly",
                allow_overages=False,
            )

        except Exception as e:
            logger.warning(f"Error obteniendo suscripción: {e}")
            return None

    def _get_period_usage(self, tenant_id: str, period_start: date) -> Dict[str, float]:
        try:
            result = (
                self.db.client.table("usage_records")
                .select("messages_count, storage_used_mb, api_calls_count")
                .eq("tenant_id", tenant_id)
                .gte("record_date", period_start.isoformat())
                .execute()
            )

            if not result.data:
                return {"messages": 0, "storage_mb": 0, "api_calls": 0}

            return {
                "messages": sum(r.get("messages_count", 0) or 0 for r in result.data),
                "storage_mb": sum(
                    r.get("storage_used_mb", 0) or 0 for r in result.data
                ),
                "api_calls": sum(r.get("api_calls_count", 0) or 0 for r in result.data),
            }

        except Exception as e:
            logger.warning(f"Error obteniendo uso del período: {e}")
            return {"messages": 0, "storage_mb": 0, "api_calls": 0}

    def _build_resource_usage(self, current: float, limit: float) -> ResourceUsage:
        if limit == -1:
            return ResourceUsage(current=current, limit=-1, percent=0, remaining=-1)
        remaining = max(0, limit - current)
        percent = (current / limit) * 100 if limit > 0 else 0
        return ResourceUsage(
            current=current, limit=limit, percent=round(percent, 2), remaining=remaining
        )


# ============================================
# Billing Calculator
# ============================================


class BillingCalculator:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def calculate_monthly_cost(
        self, tenant_id: str, period: str = "current"
    ) -> Dict[str, Any]:
        quota_checker = QuotaChecker(self.db)
        subscription = quota_checker._get_subscription(tenant_id)

        if not subscription:
            return self._empty_cost_breakdown()

        if period == "current":
            period_start = subscription.current_period_start
            period_end = subscription.current_period_end
        else:
            period_end = subscription.current_period_start - timedelta(days=1)
            period_start = period_end.replace(day=1)

        plan_limits = PlanDefinitionService.get_plan_limits(subscription.plan_key)

        base_cost = (
            plan_limits.monthly_price
            if subscription.billing_cycle == "monthly"
            else plan_limits.yearly_price / 12
        )

        usage_calc = UsageCalculator(self.db)
        summary = usage_calc.get_current_usage_summary(tenant_id)
        overage_costs = self._calculate_overages(summary, plan_limits)

        subtotal = base_cost + sum(o["cost"] for o in overage_costs)
        tax_rate = 0.08  # TODO: mover a configuración (hallazgo #9 auditoría)
        tax = round(subtotal * tax_rate, 2)
        total = subtotal + tax

        return {
            "period": {
                "start": (
                    period_start.isoformat()
                    if hasattr(period_start, "isoformat")
                    else str(period_start)
                ),
                "end": (
                    period_end.isoformat()
                    if hasattr(period_end, "isoformat")
                    else str(period_end)
                ),
            },
            "base_plan_cost": round(base_cost, 2),
            "overage_costs": overage_costs,
            "subtotal": round(subtotal, 2),
            "tax": tax,
            "total": round(total, 2),
            "currency": "USD",
        }

    def _calculate_overages(
        self, summary: UsageSummary, plan_limits: PlanLimits
    ) -> List[Dict[str, Any]]:
        overages = []

        if (
            plan_limits.messages_limit > 0
            and summary.messages.current > plan_limits.messages_limit
        ):
            overage_units = summary.messages.current - plan_limits.messages_limit
            overages.append(
                {
                    "resource": "messages",
                    "units": overage_units,
                    "rate": plan_limits.messages_overage_rate,
                    "cost": round(overage_units * plan_limits.messages_overage_rate, 2),
                }
            )

        if (
            plan_limits.storage_limit_mb > 0
            and summary.storage.current > plan_limits.storage_limit_mb
        ):
            overage_mb = summary.storage.current - plan_limits.storage_limit_mb
            overages.append(
                {
                    "resource": "storage_mb",
                    "units": round(overage_mb, 2),
                    "rate": plan_limits.storage_overage_rate,
                    "cost": round(overage_mb * plan_limits.storage_overage_rate, 2),
                }
            )

        if (
            plan_limits.api_calls_limit > 0
            and summary.api_calls.current > plan_limits.api_calls_limit
        ):
            overage_units = summary.api_calls.current - plan_limits.api_calls_limit
            overages.append(
                {
                    "resource": "api_calls",
                    "units": overage_units,
                    "rate": plan_limits.api_calls_overage_rate,
                    "cost": round(
                        overage_units * plan_limits.api_calls_overage_rate, 2
                    ),
                }
            )

        return overages

    def _empty_cost_breakdown(self) -> Dict[str, Any]:
        return {
            "period": {"start": None, "end": None},
            "base_plan_cost": 0,
            "overage_costs": [],
            "subtotal": 0,
            "tax": 0,
            "total": 0,
            "currency": "USD",
        }


# ============================================
# Invoice Generator
# ============================================


class InvoiceGenerator:

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def generate_invoice(
        self, tenant_id: str, period_start: date, period_end: date
    ) -> Optional[Invoice]:
        calc = BillingCalculator(self.db)
        cost = calc.calculate_monthly_cost(tenant_id, "current")

        invoice_number = self._generate_invoice_number(tenant_id, period_end)

        line_items = [
            LineItem(
                description=f"Plan - Período {period_start.strftime('%B %Y')}",
                quantity=1,
                unit_price=cost["base_plan_cost"],
                amount=cost["base_plan_cost"],
            )
        ]

        for overage in cost["overage_costs"]:
            line_items.append(
                LineItem(
                    description=f"{overage['resource']} extra ({overage['units']})",
                    quantity=overage["units"],
                    unit_price=overage["rate"],
                    amount=overage["cost"],
                )
            )

        subtotal = sum(li.amount for li in line_items)
        tax = cost["tax"]
        total = subtotal + tax

        try:
            result = (
                self.db.client.table("invoices")
                .insert(
                    {
                        "invoice_number": invoice_number,
                        "tenant_id": tenant_id,
                        "subscription_id": self._get_subscription_id(tenant_id),
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "subtotal": subtotal,
                        "tax_amount": tax,
                        "total_amount": total,
                        "currency": "USD",
                        "status": "draft",
                        "line_items": [li.__dict__ for li in line_items],
                    }
                )
                .execute()
            )

            return Invoice(
                id=result.data[0]["id"] if result.data else None,
                invoice_number=invoice_number,
                tenant_id=tenant_id,
                period_start=period_start,
                period_end=period_end,
                line_items=line_items,
                subtotal=subtotal,
                tax_amount=tax,
                total_amount=total,
                status="draft",
            )

        except Exception as e:
            logger.error(f"Error generando invoice: {e}")
            return None

    def _generate_invoice_number(self, tenant_id: str, period_date: date) -> str:
        year = period_date.strftime("%Y")
        tenant_code = tenant_id[:4].upper()
        try:
            result = (
                self.db.client.table("invoices")
                .select("invoice_number")
                .like("invoice_number", f"INV-{year}-%")
                .execute()
            )
            next_num = len(result.data) + 1 if result.data else 1
        except Exception:
            next_num = 1
        return f"INV-{year}-{tenant_code}-{next_num:04d}"

    def _get_subscription_id(self, tenant_id: str) -> Optional[str]:
        try:
            result = (
                self.db.client.table("tenant_subscriptions")
                .select("id")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            return result.data[0]["id"] if result.data else None
        except Exception:
            return None


# ============================================
# Usage Alert Manager
# ============================================


class UsageAlertManager:

    THRESHOLD_WARNING = 80
    THRESHOLD_CRITICAL = 100

    def __init__(self, db: Optional[SupabaseClient] = None):
        self.db = db or get_db()

    def check_and_send_alerts(self, tenant_id: str):
        summary = UsageCalculator(self.db).get_current_usage_summary(tenant_id)

        for resource_name, usage in [
            ("messages", summary.messages),
            ("storage", summary.storage),
            ("api_calls", summary.api_calls),
        ]:
            if usage.limit <= 0:
                continue
            if usage.percent >= self.THRESHOLD_WARNING:
                self._handle_threshold(
                    tenant_id,
                    resource_name,
                    usage.percent,
                    self.THRESHOLD_WARNING,
                    "warning",
                )
            if usage.percent >= self.THRESHOLD_CRITICAL:
                self._handle_threshold(
                    tenant_id,
                    resource_name,
                    usage.percent,
                    self.THRESHOLD_CRITICAL,
                    "critical",
                )

    def _handle_threshold(self, tenant_id, resource, percent, threshold, level):
        if self._alert_exists(tenant_id, resource, threshold):
            return
        self._create_alert_record(tenant_id, resource, threshold, level, percent)
        self._send_notification(tenant_id, resource, percent, threshold, level)

    def _alert_exists(self, tenant_id, resource, threshold) -> bool:
        try:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            result = (
                self.db.client.table("usage_alerts")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("alert_type", resource)
                .eq("threshold_percent", threshold)
                .gte("created_at", yesterday)
                .execute()
            )
            return len(result.data) > 0 if result.data else False
        except Exception:
            return False

    def _create_alert_record(self, tenant_id, resource, threshold, level, percent):
        try:
            self.db.client.table("usage_alerts").insert(
                {
                    "tenant_id": tenant_id,
                    "alert_type": resource,
                    "threshold_percent": threshold,
                    "usage_at_alert": {"percent": percent},
                    "is_sent": True,
                    "notification_sent_at": datetime.now(timezone.utc).isoformat(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.error(f"Error creando alerta: {e}")

    def _send_notification(self, tenant_id, resource, percent, threshold, level):
        billing_email = self._get_tenant_billing_email(tenant_id)
        alert_data = {
            "tenant_id": tenant_id,
            "alert_type": f"usage_{resource}",
            "resource": resource,
            "percent_used": round(percent, 2),
            "threshold": threshold,
            "level": level,
            "severity": "critical" if level == "critical" else "warning",
            "message": f"El uso de {resource} ha alcanzado el {percent:.1f}% del límite (threshold: {threshold}%)",
        }
        try:
            notification_service = NotificationService()
            if billing_email:
                notification_service.send_email_alert(
                    alert_data, to_email=billing_email
                )
            if notification_service.webhook_url:
                notification_service.send_webhook(alert_data)
        except Exception as e:
            logger.warning(f"NotificationService no disponible: {e}")

        logger.info(
            f"[ALERT] Tenant {tenant_id}: {resource} al {percent}% "
            f"(threshold: {threshold}%, level: {level})"
        )

    def _get_tenant_billing_email(self, tenant_id: str) -> Optional[str]:
        try:
            result = (
                self.db.client.table("tenant_subscriptions")
                .select("billing_email")
                .eq("tenant_id", tenant_id)
                .execute()
            )
            if result.data and len(result.data) > 0:
                return result.data[0].get("billing_email")
            return None
        except Exception:
            return None


# ============================================
# Helper Functions
# ============================================


def get_billing_service() -> "BillingService":
    return BillingService()


class BillingService:

    def __init__(self):
        self.plans = PlanDefinitionService()
        self.quota = QuotaChecker()
        self.usage = UsageCalculator()
        self.billing = BillingCalculator()
        self.invoices = InvoiceGenerator()
        self.alerts = UsageAlertManager()

    def get_usage(self, tenant_id: str) -> UsageSummary:
        return self.usage.get_current_usage_summary(tenant_id)

    def check_quota(self, tenant_id: str, resource: str) -> QuotaCheckResult:
        return self.quota.check_quota(tenant_id, resource)

    def get_invoices(self, tenant_id: str) -> List[Invoice]:
        return []

    def create_invoice(
        self, tenant_id: str, period_start: date, period_end: date
    ) -> Optional[Invoice]:
        return self.invoices.generate_invoice(tenant_id, period_start, period_end)
