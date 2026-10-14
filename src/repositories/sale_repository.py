"""
Sale Repository - Gestión de Ventas

Repository para manejar ventas y sus items relacionados.
Incluye operaciones para crear ventas completas, calcular totales,
y generar reportes.

Uso:
    from src.repositories.sale_repository import sale_repo
    
    # Crear venta
    sale = sale_repo.create_sale(customer_phone="+573001234567", items=[...])
    
    # Obtener ventas del día
    today_sales = sale_repo.get_sales_by_date(date.today())
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime, date, timedelta, timezone
from uuid import UUID

from src.repositories.base import BaseRepository
from src.models import Sale, SaleItem, SaleStatus, PaymentStatus
from src.core.logger import logger
from src.core.database import db
from src.core.tenant_context import TenantContextManager


class SaleItemRepository(BaseRepository[SaleItem]):
    """Repository para items de venta"""
    
    def __init__(self, client=None):
        super().__init__(
            table_name="sale_items",
            model_class=SaleItem,
            client=client or db.client
        )
    
    def get_by_sale_id(self, sale_id: UUID | str) -> List[SaleItem]:
        """
        Obtiene todos los items de una venta
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Lista de items de la venta
        """
        try:
            return self.find({"sale_id": str(sale_id)})
        except Exception as e:
            logger.error(f"❌ Error al obtener items de venta {sale_id}: {e}")
            return []


class SaleRepository(BaseRepository[Sale]):
    """
    Repository para gestionar ventas
    
    Incluye métodos para crear ventas con items,
    calcular totales, cambiar estados, y generar reportes.
    """
    
    def __init__(self, client=None):
        """Inicializa el repository de ventas"""
        super().__init__(
            table_name="sales",
            model_class=Sale,
            client=client or db.client
        )
        
        # Repository de items
        self.items_repo = SaleItemRepository(client)

    # ============================================
    # ANALYTICS
    # ============================================

    def get_top_selling_products(self, last_days: int = 30, limit: int = 10) -> List[dict]:
        """Obtiene productos más vendidos para el tenant en la ventana indicada."""
        if last_days <= 0:
            raise ValueError("last_days debe ser mayor que cero")

        safe_limit = max(1, min(limit, 50))
        start_date = (datetime.utcnow().date() - timedelta(days=min(last_days, 365) - 1)).isoformat()

        try:
            query = (
                self.client.table("sale_items")
                .select("product_id, product_name, product_sku, quantity, created_at")
                .gte("created_at", start_date)
            )
            tenant = TenantContextManager.get_current()
            if tenant and tenant.tenant_id:
                query = query.eq("tenant_id", tenant.tenant_id)
            result = query.execute()
        except Exception as e:
            logger.error(f"❌ Error al obtener productos más vendidos: {e}")
            return []

        aggregation: Dict[str, dict] = {}
        for record in result.data or []:
            key = record.get("product_id") or "unknown"
            entry = aggregation.setdefault(key, {
                "product_id": record.get("product_id"),
                "product_name": record.get("product_name"),
                "product_sku": record.get("product_sku"),
                "total_quantity": 0,
            })
            qty = record.get("quantity") or 0
            entry["total_quantity"] += int(qty)

        items = sorted(
            aggregation.values(),
            key=lambda x: (-x["total_quantity"], str(x.get("product_name") or "")),
        )
        return items[:safe_limit]
    
    # ============================================
    # CREAR VENTA COMPLETA
    # ============================================
    
    def create_sale(
        self,
        customer_phone: str,
        items: List[Dict[str, Any]],
        customer_name: Optional[str] = None,
        conversation_id: Optional[UUID | str] = None,
        payment_method: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Optional[Sale]:
        """
        Crea una venta completa con sus items
        
        Args:
            customer_phone: Teléfono del cliente
            items: Lista de items [{product_id, quantity, unit_price, ...}]
            customer_name: Nombre del cliente (opcional)
            conversation_id: ID de la conversación de WhatsApp (opcional)
            payment_method: Método de pago (opcional)
            notes: Notas adicionales (opcional)
        
        Returns:
            Venta creada o None si hay error
        
        Example:
            sale = sale_repo.create_sale(
                customer_phone="+573001234567",
                customer_name="Juan Pérez",
                items=[
                    {
                        "product_id": "uuid-del-producto",
                        "product_name": "Laptop Dell",
                        "quantity": 1,
                        "unit_price": 1299.99
                    }
                ]
            )
        """
        try:
            # 1. Calcular totales de items
            subtotal = Decimal("0")
            
            for item in items:
                quantity = item.get("quantity", 1)
                unit_price = Decimal(str(item.get("unit_price", 0)))
                discount = Decimal(str(item.get("discount", 0)))
                
                item_subtotal = (unit_price * quantity) - discount
                subtotal += item_subtotal
            
            # 2. Calcular tax (19% IVA Colombia - ajusta según tu país)
            tax = subtotal * Decimal("0.19")
            
            # 3. Total
            total = subtotal + tax
            
            # 4. Crear venta
            sale_data = {
                "customer_phone": customer_phone,
                "customer_name": customer_name,
                "conversation_id": str(conversation_id) if conversation_id else None,
                "status": SaleStatus.PENDING.value,
                "subtotal": float(subtotal),
                "tax": float(tax),
                "discount": 0.0,
                "total": float(total),
                "payment_method": payment_method,
                "payment_status": PaymentStatus.PENDING.value,
                "notes": notes
            }
            
            sale = self.create(sale_data)
            
            if not sale:
                logger.error("❌ No se pudo crear la venta")
                return None
            
            # 5. Crear items de venta
            for item_data in items:
                # Calcular totales del item
                quantity = item_data.get("quantity", 1)
                unit_price = Decimal(str(item_data.get("unit_price", 0)))
                discount = Decimal(str(item_data.get("discount", 0)))
                
                item_subtotal = unit_price * quantity
                item_total = item_subtotal - discount
                
                # Crear item
                sale_item_data = {
                    "sale_id": str(sale.id),
                    "product_id": str(item_data["product_id"]),
                    "product_name": item_data["product_name"],
                    "product_sku": item_data.get("product_sku"),
                    "quantity": quantity,
                    "unit_price": float(unit_price),
                    "subtotal": float(item_subtotal),
                    "discount": float(discount),
                    "total": float(item_total)
                }
                
                self.items_repo.create(sale_item_data)
            
            logger.success(f"✅ Venta creada: {sale.id} - Total: ${total}")
            return sale
            
        except Exception as e:
            logger.error(f"❌ Error al crear venta: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    # ============================================
    # OBTENER VENTA CON ITEMS
    # ============================================
    
    def get_sale_with_items(self, sale_id: UUID | str) -> Optional[Sale]:
        """
        Obtiene una venta con sus items cargados
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Venta con items o None
        """
        try:
            # Obtener venta
            sale = self.get_by_id(sale_id)
            
            if not sale:
                return None
            
            # Cargar items
            items = self.items_repo.get_by_sale_id(sale_id)
            sale.items = items
            
            logger.debug(f"📦 Venta {sale_id} con {len(items)} items")
            return sale
            
        except Exception as e:
            logger.error(f"❌ Error al obtener venta con items: {e}")
            return None
    
    # ============================================
    # CAMBIAR ESTADOS
    # ============================================
    
    def confirm_sale(self, sale_id: UUID | str) -> Optional[Sale]:
        """
        Confirma una venta
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Venta actualizada o None
        """
        try:
            return self.update(sale_id, {
                "status": SaleStatus.CONFIRMED.value,
                "confirmed_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"❌ Error al confirmar venta: {e}")
            return None
    
    def cancel_sale(self, sale_id: UUID | str) -> Optional[Sale]:
        """
        Cancela una venta
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Venta actualizada o None
        """
        try:
            return self.update(sale_id, {
                "status": SaleStatus.CANCELLED.value
            })
        except Exception as e:
            logger.error(f"❌ Error al cancelar venta: {e}")
            return None
    
    def complete_sale(self, sale_id: UUID | str) -> Optional[Sale]:
        """
        Completa una venta
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Venta actualizada o None
        """
        try:
            return self.update(sale_id, {
                "status": SaleStatus.COMPLETED.value,
                "completed_at": datetime.utcnow().isoformat()
            })
        except Exception as e:
            logger.error(f"❌ Error al completar venta: {e}")
            return None
    
    def mark_as_paid(self, sale_id: UUID | str) -> Optional[Sale]:
        """
        Marca una venta como pagada
        
        Args:
            sale_id: ID de la venta
        
        Returns:
            Venta actualizada o None
        """
        try:
            return self.update(sale_id, {
                "payment_status": PaymentStatus.PAID.value
            })
        except Exception as e:
            logger.error(f"❌ Error al marcar como pagada: {e}")
            return None
    
    # ============================================
    # BÚSQUEDAS POR CLIENTE
    # ============================================
    
    def get_by_customer(
        self,
        customer_phone: str,
        limit: int = 100
    ) -> List[Sale]:
        """
        Obtiene ventas de un cliente
        
        Args:
            customer_phone: Teléfono del cliente
            limit: Número máximo de ventas
        
        Returns:
            Lista de ventas del cliente
        """
        try:
            return self.find({"customer_phone": customer_phone}, limit=limit)
        except Exception as e:
            logger.error(f"❌ Error al obtener ventas del cliente: {e}")
            return []
    
    def get_by_conversation(
        self,
        conversation_id: UUID | str,
        limit: int = 100
    ) -> List[Sale]:
        """
        Obtiene ventas de una conversación
        
        Args:
            conversation_id: ID de la conversación
            limit: Número máximo de ventas
        
        Returns:
            Lista de ventas de la conversación
        """
        try:
            return self.find(
                {"conversation_id": str(conversation_id)},
                limit=limit
            )
        except Exception as e:
            logger.error(f"❌ Error al obtener ventas de conversación: {e}")
            return []
    
    # ============================================
    # BÚSQUEDAS POR FECHA
    # ============================================
    
    def get_sales_by_date(
        self,
        target_date: date,
        limit: int = 1000
    ) -> List[Sale]:
        """
        Obtiene ventas de una fecha específica
        
        Args:
            target_date: Fecha a consultar
            limit: Número máximo de ventas
        
        Returns:
            Lista de ventas del día
        """
        try:
            # Rango: desde inicio del día hasta fin del día
            start = datetime.combine(target_date, datetime.min.time())
            end = datetime.combine(target_date, datetime.max.time())
            
            result = (
                self.client.table(self.table_name)
                .select("*")
                .gte("created_at", start.isoformat())
                .lte("created_at", end.isoformat())
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            
            sales = [Sale(**record) for record in result.data]
            
            logger.debug(f"📅 Ventas del {target_date}: {len(sales)}")
            return sales
            
        except Exception as e:
            logger.error(f"❌ Error al obtener ventas por fecha: {e}")
            return []
    
    def get_sales_by_date_range(
        self,
        start_date: date,
        end_date: date,
        limit: int = 1000,
        tenant_id: str | None = None,
        status: str | None = None,
    ) -> List[Sale]:
        """
        Obtiene ventas en un rango de fechas
        
        Args:
            start_date: Fecha inicial
            end_date: Fecha final
            limit: Número máximo de ventas
        
        Returns:
            Lista de ventas en el rango
        """
        try:
            start = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            end = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
            
            query = (
                self.client.table(self.table_name)
                .select("*")
                .gte("created_at", start.isoformat().replace("+00:00", "Z"))
                .lte("created_at", end.isoformat().replace("+00:00", "Z"))
                .order("created_at", desc=True)
                .limit(limit)
            )

            # Filtrar por tenant y estado si se especifican
            if tenant_id:
                query = query.eq("tenant_id", tenant_id)
            if status:
                status_normalized = str(status).lower()
                query = query.eq("status", status_normalized)

            result = query.execute()
            
            sales = [Sale(**record) for record in result.data]

            
            logger.debug(f"📅 Ventas entre {start_date} y {end_date}: {len(sales)}")
            return sales
            
        except Exception as e:
            logger.error(f"❌ Error al obtener ventas por rango: {e}")
            return []
    
    # ============================================
    # REPORTES Y ESTADÍSTICAS
    # ============================================
    
    def get_daily_report(self, target_date: date = None) -> Dict[str, Any]:
        """
        Genera reporte de ventas del día
        
        Args:
            target_date: Fecha del reporte (hoy si es None)
        
        Returns:
            Diccionario con estadísticas del día
        """
        try:
            if not target_date:
                target_date = date.today()
            
            sales = self.get_sales_by_date(target_date)
            
            report = {
                "date": target_date.isoformat(),
                "total_sales": len(sales),
                "total_revenue": sum(Decimal(str(s.total)) for s in sales),
                "confirmed_sales": len([s for s in sales if s.status == SaleStatus.CONFIRMED]),
                "pending_sales": len([s for s in sales if s.status == SaleStatus.PENDING]),
                "cancelled_sales": len([s for s in sales if s.status == SaleStatus.CANCELLED]),
                "paid_sales": len([s for s in sales if s.payment_status == PaymentStatus.PAID]),
                "average_sale": Decimal("0")
            }
            
            if report["total_sales"] > 0:
                report["average_sale"] = report["total_revenue"] / report["total_sales"]
            
            logger.debug(f"📊 Reporte del {target_date}: {report['total_sales']} ventas")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error al generar reporte diario: {e}")
            return {}
    
    def get_monthly_report(self, year: int = None, month: int = None) -> Dict[str, Any]:
        """
        Genera reporte de ventas del mes
        
        Args:
            year: Año (año actual si es None)
            month: Mes (mes actual si es None)
        
        Returns:
            Diccionario con estadísticas del mes
        """
        try:
            if not year or not month:
                today = date.today()
                year = today.year
                month = today.month
            
            # Primer y último día del mes
            start_date = date(year, month, 1)
            
            # Último día del mes
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
            
            sales = self.get_sales_by_date_range(start_date, end_date)
            
            report = {
                "year": year,
                "month": month,
                "total_sales": len(sales),
                "total_revenue": sum(Decimal(str(s.total)) for s in sales),
                "confirmed_sales": len([s for s in sales if s.status == SaleStatus.CONFIRMED]),
                "unique_customers": len(set(s.customer_phone for s in sales)),
                "average_sale": Decimal("0"),
                "best_day": None,
                "best_day_revenue": Decimal("0")
            }
            
            if report["total_sales"] > 0:
                report["average_sale"] = report["total_revenue"] / report["total_sales"]
            
            # Encontrar mejor día
            daily_totals = {}
            for sale in sales:
                day = sale.created_at.date()
                if day not in daily_totals:
                    daily_totals[day] = Decimal("0")
                daily_totals[day] += Decimal(str(sale.total))
            
            if daily_totals:
                best_day = max(daily_totals.items(), key=lambda x: x[1])
                report["best_day"] = best_day[0].isoformat()
                report["best_day_revenue"] = best_day[1]
            
            logger.debug(f"📊 Reporte del mes {month}/{year}: {report['total_sales']} ventas")
            return report
            
        except Exception as e:
            logger.error(f"❌ Error al generar reporte mensual: {e}")
            return {}


# ============================================
# INSTANCIAS GLOBALES
# ============================================
sale_repo = SaleRepository()
sale_item_repo = SaleItemRepository()


# ============================================
# EJEMPLO DE USO
# ============================================
if __name__ == "__main__":
    from src.core.tenant_context import TenantContextManager
    from datetime import date
    
    # Configurar tenant
    tenant_manager = TenantContextManager()
    tenant_manager.set_tenant("00000000-0000-0000-0000-000000000001")
    
    print("\n💰 SALE REPOSITORY - EJEMPLOS")
    print("=" * 60)
    
    # 1. Reporte diario
    print("\n1️⃣ Reporte de ventas del día:")
    report = sale_repo.get_daily_report()
    for key, value in report.items():
        print(f"  {key}: {value}")
    
    # 2. Ventas por cliente
    print("\n2️⃣ Ventas de un cliente:")
    customer_sales = sale_repo.get_by_customer("+573001234567")
    print(f"  Total: {len(customer_sales)} ventas")
    
    print("\n" + "=" * 60)