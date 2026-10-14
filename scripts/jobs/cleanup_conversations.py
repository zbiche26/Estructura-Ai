"""
Job: Limpiar Conversaciones Antiguas
=====================================

Este script elimina conversaciones y mensajes mayores a 90 días.

Uso:
    python scripts/jobs/cleanup_conversations.py
    python scripts/jobs/cleanup_conversations.py --days 90
    python scripts/jobs/cleanup_conversations.py --dry-run

TAREA 12: Job para limpiar conversaciones antiguas (>90 días)
"""

import argparse
import sys
from datetime import datetime, timedelta
from typing import List

sys.path.insert(0, 'c:/Users/crist/backEstructuraAI')

from src.core.database import db
from src.core.logger import logger


# ============================================
# CONFIGURACIÓN
# ============================================

DEFAULT_DAYS = 90  # Mantener conversaciones de los últimos 90 días


# ============================================
# FUNCIONES DE LIMPIEZA
# ============================================

def get_conversations_to_delete(cutoff_date: str, tenant_id: str = None) -> List[str]:
    """
    Obtiene los IDs de conversaciones que deben eliminarse.
    
    Args:
        cutoff_date: Fecha límite (ISO string)
        tenant_id: Filtrar por tenant (opcional)
    
    Returns:
        Lista de IDs de conversaciones
    """
    try:
        query = db.client.table('conversations').select('id').lt('created_at', cutoff_date)
        
        if tenant_id:
            query = query.eq('tenant_id', tenant_id)
        
        response = query.execute()
        return [c['id'] for c in response.data or []]
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo conversaciones: {e}")
        return []


def delete_messages_for_conversations(conversation_ids: List[str]) -> int:
    """
    Elimina mensajes de las conversaciones.
    
    Args:
        conversation_ids: Lista de IDs de conversaciones
    
    Returns:
        Número de mensajes eliminados
    """
    if not conversation_ids:
        return 0
    
    try:
        # Contar mensajes a eliminar
        count_response = db.client.table('messages').select('id', count='exact').in_('conversation_id', conversation_ids).execute()
        messages_count = count_response.count or 0
        
        # Eliminar mensajes
        db.client.table('messages').delete().in_('conversation_id', conversation_ids).execute()
        
        logger.info(f"🗑️ {messages_count} mensajes eliminados")
        return messages_count
        
    except Exception as e:
        logger.error(f"❌ Error eliminando mensajes: {e}")
        return 0


def delete_conversations(conversation_ids: List[str]) -> int:
    """
    Elimina las conversaciones.
    
    Args:
        conversation_ids: Lista de IDs de conversaciones
    
    Returns:
        Número de conversaciones eliminadas
    """
    if not conversation_ids:
        return 0
    
    try:
        db.client.table('conversations').delete().in_('id', conversation_ids).execute()
        
        logger.info(f"🗑️ {len(conversation_ids)} conversaciones eliminadas")
        return len(conversation_ids)
        
    except Exception as e:
        logger.error(f"❌ Error eliminando conversaciones: {e}")
        return 0


def cleanup_old_conversations(days: int = DEFAULT_DAYS, tenant_id: str = None, dry_run: bool = False):
    """
    Limpia conversaciones y mensajes antiguos.
    
    Args:
        days: Días a mantener (default 90)
        tenant_id: Filtrar por tenant (opcional)
        dry_run: Si True, solo muestra lo que se eliminaría
    """
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    logger.info(f"🧹 Iniciando limpieza de conversaciones > {days} días")
    logger.info(f"📅 Fecha límite: {cutoff_date}")
    
    if dry_run:
        logger.info("🔍 Modo DRY RUN - No se eliminará nada")
    
    # Obtener conversaciones a eliminar
    conversation_ids = get_conversations_to_delete(cutoff_date, tenant_id)
    
    if not conversation_ids:
        logger.info("✅ No hay conversaciones para eliminar")
        return
    
    logger.info(f"📋 {len(conversation_ids)} conversaciones encontradas para eliminar")
    
    if dry_run:
        logger.info(f"🔍 Se eliminarían {len(conversation_ids)} conversaciones")
        return
    
    # Eliminar mensajes primero (foreign key)
    messages_deleted = delete_messages_for_conversations(conversation_ids)
    
    # Eliminar conversaciones
    conversations_deleted = delete_conversations(conversation_ids)
    
    logger.info(f"✅ Limpieza completada: {conversations_deleted} conversaciones, {messages_deleted} mensajes")


# ============================================
# PUNTO DE ENTRADA
# ============================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Limpiar conversaciones antiguas')
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS, help=f'Días a mantener (default: {DEFAULT_DAYS})')
    parser.add_argument('--tenant-id', type=str, help='ID específico del tenant')
    parser.add_argument('--dry-run', action='store_true', help='Solo mostrar qué se eliminaría')
    
    args = parser.parse_args()
    
    cleanup_old_conversations(
        days=args.days,
        tenant_id=args.tenant_id,
        dry_run=args.dry_run
    )
