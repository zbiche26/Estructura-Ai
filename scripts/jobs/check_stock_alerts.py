"""
Job para revisar alertas de stock
Ejecutar cada hora vía cron/scheduler
"""

from src.services.stock_alerts import StockAlertService
from src.core.logger import logger


def run():
    """Ejecuta revisión de alertas de stock bajo"""
    try:
        logger.info("🔍 Iniciando revisión de stock...")
        
        service = StockAlertService()
        alerts = service.check_low_stock(threshold=10)
        
        # Contar por severidad
        critical = sum(1 for a in alerts if a['severity'] == 'critical')
        warning = sum(1 for a in alerts if a['severity'] == 'warning')
        
        logger.success(f"✅ {len(alerts)} alertas generadas")
        logger.info(f"   - Critical: {critical}")
        logger.info(f"   - Warning: {warning}")
        
        return alerts
        
    except Exception as e:
        logger.error(f"❌ Error en job de alertas: {str(e)}")
        raise


if __name__ == "__main__":
    run()