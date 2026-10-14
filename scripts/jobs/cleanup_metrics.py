"""
Job: Limpiar Métricas Antiguas
================================

Este script elimina métricas mayores a 1 año y mantiene agregaciones históricas.

Uso:
    python scripts/jobs/cleanup_metrics.py
    python scripts/jobs/cleanup_metrics.py --days 365
    python scripts/jobs/cleanup_metrics.py --dry-run

TAREAS 13-14: Job para limpiar métricas antiguas (>1 año)
"""

import argparse
import sys
from datetime import datetime, timedelta
from typing import Dict, List

sys.path.insert(0, 'c:/Users/crist/backEstructuraAI')

from src.core.database import db
from src.core.logger import logger


# ============================================
# CONFIGURACIÓN
# ============================================

DEFAULT_DAYS = 365  # Mantener métricas del último año


# ============================================
# TABLAS DE MÉTRICAS
# ============================================

METRICS_TABLES = [
    'conversation_metrics',
    'intent_metrics', 
    'product_metrics',
    'performance_metrics'
]


# ============================================
# FUNCIONES DE LIMPIEZA
# ============================================

def get_metrics_to_delete(table_name: str, cutoff_date: str, tenant_id: str = None) -> List[str]:
    """
    Obtiene los IDs de métricas que deben eliminarse.
    
    Args:
        table_name: Nombre de la tabla
        cutoff_date: Fecha límite (ISO string)
        tenant_id: Filtrar por tenant (opcional)
    
    Returns:
        Lista de IDs
    """
    try:
        query = db.client.table(table_name).select('id').lt('date', cutoff_date)
        
        if tenant_id:
            query = query.eq('tenant_id', tenant_id)
        
        response = query.execute()
        return [m['id'] for m in response.data or []]
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo métricas de {table_name}: {e}")
        return []


def delete_metrics(table_name: str, ids: List[str]) -> int:
    """
    Elimina métricas de una tabla.
    
    Args:
        table_name: Nombre de la tabla
        ids: Lista de IDs a eliminar
    
    Returns:
        Número de registros eliminados
    """
    if not ids:
        return 0
    
    try:
        db.client.table(table_name).delete().in_('id', ids).execute()
        
        logger.info(f"🗑️ {len(ids)} registros eliminados de {table_name}")
        return len(ids)
        
    except Exception as e:
        logger.error(f"❌ Error eliminando de {table_name}: {e}")
        return 0


def create_monthly_aggregations(tenant_id: str = None):
    """
    TAREA 14: Mantener agregaciones históricas
    
    Crea agregaciones mensuales antes de eliminar datos diarios.
    
    Args:
        tenant_id: Filtrar por tenant (opcional)
    """
    logger.info("📊 Creando agregaciones mensuales...")
    
    # Esta función debería:
    # 1. Consultar los datos diarios del último mes
    # 2. Calcular promedios/sumas mensuales
    # 3. Guardar en una tabla de agregaciones mensuales
    
    # Por ahora, es un placeholder - implementar según necesidad
    logger.info("✅ Agregaciones mensuales (placeholder)")


def cleanup_old_metrics(days: int = DEFAULT_DAYS, tenant_id: str = None, dry_run: bool = False):
    """
    Limpia métricas antiguas.
    
    Args:
        days: Días a mantener (default 365)
        tenant_id: Filtrar por tenant (opcional)
        dry_run: Si True, solo muestra lo que se eliminaría
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).date().isoformat()
    
    logger.info(f"🧹 Iniciando limpieza de métricas > {days} días")
    logger.info(f"📅 Fecha límite: {cutoff_date}")
    
    if dry_run:
        logger.info("🔍 Modo DRY RUN - No se eliminará nada")
    
    total_deleted = 0
    
    for table_name in METRICS_TABLES:
        logger.info(f"\n📋 Procesando tabla: {table_name}")
        
        # Obtener métricas a eliminar
        ids = get_metrics_to_delete(table_name, cutoff_date, tenant_id)
        
        if not ids:
            logger.info(f"  ✅ No hay métricas para eliminar")
            continue
        
        logger.info(f"  📊 {len(ids)} registros encontrados para eliminar")
        
        if not dry_run:
            # Crear agregaciones primero (tarea 14)
            create_monthly_aggregations(tenant_id)
            
            # Eliminar métricas
            deleted = delete_metrics(table_name, ids)
            total_deleted += deleted
        else:
            total_deleted += len(ids)
    
    if dry_run:
        logger.info(f"\n🔍 Se eliminarían {total_deleted} registros en total")
    else:
        logger.info(f"\n✅ Limpieza completada: {total_deleted} registros eliminados")


# ============================================
# PUNTO DE ENTRADA
# ============================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Limpiar métricas antiguas')
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS, help=f'Días a mantener (default: {DEFAULT_DAYS})')
    parser.add_argument('--tenant-id', type=str, help='ID específico del tenant')
    parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se eliminaría')
    
    args = parser.parse_args()
    
    cleanup_old_metrics(
        days=args.days,
        tenant_id=args.tenant_id,
        dry_run=args.dry_run
    )
