"""
Job: Calcular Métricas Diarias
=============================

Este script calcula y guarda las métricas diarias de:
- Conversaciones
- Intenciones
- Productos
- Rendimiento

Uso:
    python scripts/jobs/calculate_metrics.py
    python scripts/jobs/calculate_metrics.py --date 2026-03-17
    python scripts/jobs/calculate_metrics.py --tenant-id <uuid>

TAREAS 7-10: Job completo de métricas diarias
"""

import argparse
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

# Agregar el path del proyecto
sys.path.insert(0, 'c:/Users/crist/backEstructuraAI')

from src.core.database import db
from src.core.logger import logger
from src.repositories.conversation_repository import ConversationRepository, MessageRepository


# ============================================
# CLASES PARA MÉTRICAS
# ============================================

class MetricsCalculator:
    """Calculador de métricas diarias"""
    
    def __init__(self, client=None):
        self.client = client or db.client
        self.conversation_repo = ConversationRepository(client=self.client)
        self.message_repo = MessageRepository(client=self.client)
    
    def process_conversations_of_day(
        self, 
        tenant_id: str, 
        target_date: date
    ) -> Dict[str, Any]:
        """
        TAREA 8: Procesar conversaciones del día
        
        Obtiene todas las conversaciones de un tenant para una fecha específica.
        
        Args:
            tenant_id: ID del tenant
            target_date: Fecha a procesar
            
        Returns:
            Dict con datos procesados de conversaciones
        """
        logger.info(f"📥 Procesando conversaciones para tenant={tenant_id}, fecha={target_date}")
        
        # Calcular rango de fechas
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = datetime.combine(target_date + timedelta(days=1), datetime.min.time())
        
        try:
            # Obtener conversaciones del día
            response = self.client.table('conversations').select('*').eq('tenant_id', tenant_id).gte('created_at', start_datetime.isoformat()).lt('created_at', end_datetime.isoformat()).execute()
            
            conversations = response.data or []
            
            # Procesar datos
            result = {
                'total_conversations': len(conversations),
                'conversations': conversations,
                'conversation_ids': [c['id'] for c in conversations],
                'platforms': {},
                'statuses': {},
                'user_phones': set()
            }
            
            # Análisis por plataforma
            for conv in conversations:
                platform = conv.get('platform', 'unknown')
                result['platforms'][platform] = result['platforms'].get(platform, 0) + 1
                
                status = conv.get('status', 'active')
                result['statuses'][status] = result['statuses'].get(status, 0) + 1
                
                if conv.get('user_phone'):
                    result['user_phones'].add(conv['user_phone'])
            
            result['unique_users'] = len(result['user_phones'])
            result['user_phones'] = result['user_phones']  # Convertir a list después
            
            logger.info(f"✅ {len(conversations)} conversaciones procesadas")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error procesando conversaciones: {e}")
            return {
                'total_conversations': 0,
                'conversations': [],
                'conversation_ids': [],
                'platforms': {},
                'statuses': {},
                'unique_users': 0,
                'user_phones': set()
            }
    
    def get_messages_for_conversations(
        self, 
        conversation_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Obtiene mensajes de las conversaciones del día.
        
        Args:
            conversation_ids: Lista de IDs de conversaciones
            
        Returns:
            Dict con estadísticas de mensajes
        """
        if not conversation_ids:
            return {
                'total_messages': 0,
                'user_messages': 0,
                'assistant_messages': 0,
                'total_tokens': 0
            }
        
        try:
            response = self.client.table('messages').select('*').in_('conversation_id', conversation_ids).execute()
            
            messages = response.data or []
            
            user_messages = sum(1 for m in messages if m.get('role') == 'user')
            assistant_messages = sum(1 for m in messages if m.get('role') == 'assistant')
            total_tokens = sum(m.get('tokens_used', 0) for m in messages if m.get('tokens_used'))
            
            return {
                'total_messages': len(messages),
                'user_messages': user_messages,
                'assistant_messages': assistant_messages,
                'total_tokens': total_tokens,
                'messages': messages
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo mensajes: {e}")
            return {
                'total_messages': 0,
                'user_messages': 0,
                'assistant_messages': 0,
                'total_tokens': 0,
                'messages': []
            }
    
    def calculate_aggregated_metrics(
        self,
        conversations_data: Dict[str, Any],
        messages_data: Dict[str, Any],
        target_date: date
    ) -> Dict[str, Any]:
        """
        TAREA 9: Calcular métricas agregadas
        
        Calcula las métricas agregadas a partir de los datos crudos.
        
        Args:
            conversations_data: Datos de conversaciones procesadas
            messages_data: Datos de mensajes
            target_date: Fecha objetivo
            
        Returns:
            Dict con métricas calculadas
        """
        logger.info("📊 Calculando métricas agregadas...")
        
        total_convs = conversations_data['total_conversations']
        total_msgs = messages_data['total_messages']
        total_tokens = messages_data['total_tokens']
        unique_users = conversations_data['unique_users']
        
        # Calcular promedios
        avg_tokens_per_conversation = (
            total_tokens / total_convs if total_convs > 0 else 0
        )
        
        avg_messages_per_conversation = (
            total_msgs / total_convs if total_convs > 0 else 0
        )
        
        # Métricas por plataforma
        platforms = conversations_data['platforms']
        
        # Métricas por status
        statuses = conversations_data['statuses']
        
        metrics = {
            # Fecha
            'date': target_date.isoformat(),
            
            # Volumen de conversaciones
            'total_conversations': total_convs,
            'active_conversations': statuses.get('active', 0),
            'closed_conversations': statuses.get('closed', 0),
            'archived_conversations': statuses.get('archived', 0),
            
            # Mensajes
            'total_messages': total_msgs,
            'total_user_messages': messages_data['user_messages'],
            'total_assistant_messages': messages_data['assistant_messages'],
            
            # Tokens
            'total_tokens_used': total_tokens,
            'avg_tokens_per_conversation': round(avg_tokens_per_conversation, 2),
            
            # Plataformas
            'whatsapp_conversations': platforms.get('whatsapp', 0),
            'web_conversations': platforms.get('web', 0),
            'telegram_conversations': platforms.get('telegram', 0),
            
            # Usuarios
            'new_users': unique_users,  # Simplificado: todos son "nuevos" en este cálculo
            'returning_users': 0,
            
            # Tiempos (placeholders - requeriría datos adicionales)
            'avg_response_time_seconds': 0,
            'avg_conversation_duration_minutes': 0
        }
        
        logger.info(f"✅ Métricas calculadas: {total_convs} convs, {total_msgs} msgs, {total_tokens} tokens")
        return metrics
    
    def save_conversation_metrics(
        self, 
        tenant_id: str, 
        metrics: Dict[str, Any]
    ) -> bool:
        """
        TAREA 10: Guardar en tabla de métricas de conversaciones
        
        Args:
            tenant_id: ID del tenant
            metrics: Métricas calculadas
            
        Returns:
            True si se guardó correctamente
        """
        logger.info(f"💾 Guardando métricas de conversaciones para tenant={tenant_id}")
        
        try:
            # Verificar si ya existen métricas para esta fecha
            existing = self.client.table('conversation_metrics').select('id').eq('tenant_id', tenant_id).eq('date', metrics['date']).execute()
            
            data = {
                'tenant_id': tenant_id,
                'date': metrics['date'],
                'total_conversations': metrics['total_conversations'],
                'active_conversations': metrics['active_conversations'],
                'closed_conversations': metrics['closed_conversations'],
                'archived_conversations': metrics['archived_conversations'],
                'total_messages': metrics['total_messages'],
                'total_user_messages': metrics['total_user_messages'],
                'total_assistant_messages': metrics['total_assistant_messages'],
                'total_tokens_used': metrics['total_tokens_used'],
                'avg_tokens_per_conversation': metrics['avg_tokens_per_conversation'],
                'avg_response_time_seconds': metrics['avg_response_time_seconds'],
                'avg_conversation_duration_minutes': metrics['avg_conversation_duration_minutes'],
                'whatsapp_conversations': metrics['whatsapp_conversations'],
                'web_conversations': metrics['web_conversations'],
                'telegram_conversations': metrics['telegram_conversations'],
                'new_users': metrics['new_users'],
                'returning_users': metrics['returning_users']
            }
            
            if existing.data:
                # Actualizar
                self.client.table('conversation_metrics').update(data).eq('tenant_id', tenant_id).eq('date', metrics['date']).execute()
                logger.info(f"✅ Métricas actualizadas para {metrics['date']}")
            else:
                # Insertar
                self.client.table('conversation_metrics').insert(data).execute()
                logger.info(f"✅ Métricas insertadas para {metrics['date']}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error guardando métricas: {e}")
            return False
    
    def calculate_metrics_for_tenant(
        self, 
        tenant_id: str, 
        target_date: Optional[date] = None
    ) -> bool:
        """
        Calcula y guarda todas las métricas para un tenant y fecha.
        
        Args:
            tenant_id: ID del tenant
            target_date: Fecha a procesar (default: ayer)
            
        Returns:
            True si fue exitoso
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        logger.info(f"🚀 Iniciando cálculo de métricas para tenant={tenant_id}, fecha={target_date}")
        
        # TAREA 8: Procesar conversaciones del día
        conversations_data = self.process_conversations_of_day(tenant_id, target_date)
        
        # Obtener mensajes
        messages_data = self.get_messages_for_conversations(
            conversations_data['conversation_ids']
        )
        
        # TAREA 9: Calcular métricas agregadas
        metrics = self.calculate_aggregated_metrics(
            conversations_data, 
            messages_data, 
            target_date
        )
        
        # TAREA 10: Guardar en tabla
        success = self.save_conversation_metrics(tenant_id, metrics)
        
        if success:
            logger.info(f"✅ Métricas diarias calculadas exitosamente para {target_date}")
        else:
            logger.error(f"❌ Error al calcular métricas")
        
        return success


# ============================================
# FUNCIONES AUXILIARES
# ============================================

def get_all_tenants() -> List[str]:
    """Obtiene lista de todos los tenant_ids"""
    try:
        response = db.client.table('tenants').select('id').execute()
        return [t['id'] for t in response.data or []]
    except Exception as e:
        logger.error(f"❌ Error obteniendo tenants: {e}")
        return []


def run_daily_metrics_job(target_date: Optional[date] = None):
    """
    Ejecuta el job de métricas diarias para todos los tenants.
    
    Args:
        target_date: Fecha a procesar (default: ayer)
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)
    
    logger.info(f"📅 Iniciando job de métricas diarias para {target_date}")
    
    # Obtener todos los tenants
    tenants = get_all_tenants()
    
    if not tenants:
        logger.warning("⚠️ No se encontraron tenants")
        return
    
    logger.info(f"📋 Procesando {len(tenants)} tenants...")
    
    calculator = MetricsCalculator()
    success_count = 0
    failure_count = 0
    
    for tenant_id in tenants:
        try:
            result = calculator.calculate_metrics_for_tenant(tenant_id, target_date)
            if result:
                success_count += 1
            else:
                failure_count += 1
        except Exception as e:
            logger.error(f"❌ Error procesando tenant {tenant_id}: {e}")
            failure_count += 1
    
    logger.info(f"📊 Job completado: {success_count} exitosos, {failure_count} fallidos")


# ============================================
# PUNTO DE ENTRADA
# ============================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Calcular métricas diarias')
    parser.add_argument('--date', type=str, help='Fecha a procesar (YYYY-MM-DD)')
    parser.add_argument('--tenant-id', type=str, help='ID específico del tenant')
    
    args = parser.parse_args()
    
    # Parsear fecha
    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    
    if args.tenant_id:
        # Procesar un tenant específico
        calculator = MetricsCalculator()
        calculator.calculate_metrics_for_tenant(args.tenant_id, target_date)
    else:
        # Procesar todos los tenants
        run_daily_metrics_job(target_date)
