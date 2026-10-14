"""
Tests de Jobs de Analytics
==========================

Tests para validar los jobs de métricas diarias y limpieza.
TAREA 17: Tests de jobs (15 tests)
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4


# ============================================
# TESTS PARA MetricsCalculator
# ============================================

class TestMetricsCalculator:
    """Tests para el calculador de métricas"""
    
    @pytest.fixture
    def mock_client(self):
        """Mock del cliente de Supabase"""
        client = MagicMock()
        return client
    
    @pytest.fixture
    def calculator(self, mock_client):
        """Crea instancia del calculador con mock"""
        from scripts.jobs.calculate_metrics import MetricsCalculator
        calculator = MetricsCalculator(client=mock_client)
        return calculator
    
    def test_calculator_init(self, calculator):
        """Test: Calculador se inicializa"""
        assert calculator is not None
        assert calculator.client is not None
    
    def test_process_conversations_of_day_returns_dict(self, calculator, mock_client):
        """Test: Retorna diccionario con datos de conversaciones"""
        mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.lt.return_value.execute.return_value.data = []
        
        result = calculator.process_conversations_of_day(str(uuid4()), date.today())
        
        assert isinstance(result, dict)
        assert 'total_conversations' in result
        assert 'conversations' in result
    
    def test_process_conversations_counts_platforms(self, calculator, mock_client):
        """Test: Cuenta conversaciones por plataforma"""
        mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.lt.return_value.execute.return_value.data = [
            {'id': '1', 'platform': 'whatsapp', 'status': 'active', 'user_phone': '+573001234567'},
            {'id': '2', 'platform': 'whatsapp', 'status': 'closed', 'user_phone': '+573001234567'},
            {'id': '3', 'platform': 'web', 'status': 'active', 'user_phone': '+573008765432'},
        ]
        
        result = calculator.process_conversations_of_day(str(uuid4()), date.today())
        
        assert result['platforms']['whatsapp'] == 2
        assert result['platforms']['web'] == 1
    
    def test_process_conversations_counts_statuses(self, calculator, mock_client):
        """Test: Cuenta conversaciones por status"""
        mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.lt.return_value.execute.return_value.data = [
            {'id': '1', 'platform': 'whatsapp', 'status': 'active'},
            {'id': '2', 'platform': 'whatsapp', 'status': 'closed'},
            {'id': '3', 'platform': 'web', 'status': 'archived'},
        ]
        
        result = calculator.process_conversations_of_day(str(uuid4()), date.today())
        
        assert result['statuses']['active'] == 1
        assert result['statuses']['closed'] == 1
        assert result['statuses']['archived'] == 1
    
    def test_get_messages_for_conversations_empty(self, calculator, mock_client):
        """Test: Retorna datos vacíos para lista vacía"""
        result = calculator.get_messages_for_conversations([])
        
        assert result['total_messages'] == 0
        assert result['user_messages'] == 0
    
    def test_get_messages_for_conversations_with_data(self, calculator, mock_client):
        """Test: Obtiene mensajes correctamente"""
        mock_client.table.return_value.select.return_value.in_.return_value.execute.return_value.data = [
            {'id': '1', 'role': 'user', 'tokens_used': 10},
            {'id': '2', 'role': 'assistant', 'tokens_used': 20},
            {'id': '3', 'role': 'user', 'tokens_used': 15},
        ]
        
        result = calculator.get_messages_for_conversations(['conv1', 'conv2'])
        
        assert result['total_messages'] == 3
        assert result['user_messages'] == 2
        assert result['assistant_messages'] == 1
        assert result['total_tokens'] == 45
    
    def test_calculate_aggregated_metrics(self, calculator):
        """Test: Calcula métricas agregadas correctamente"""
        conversations_data = {
            'total_conversations': 10,
            'conversation_ids': ['1', '2'],
            'platforms': {'whatsapp': 8, 'web': 2},
            'statuses': {'active': 5, 'closed': 5},
            'unique_users': 10
        }
        
        messages_data = {
            'total_messages': 100,
            'user_messages': 50,
            'assistant_messages': 50,
            'total_tokens': 5000
        }
        
        target_date = date.today()
        
        result = calculator.calculate_aggregated_metrics(
            conversations_data, messages_data, target_date
        )
        
        assert result['total_conversations'] == 10
        assert result['total_messages'] == 100
        assert result['total_tokens_used'] == 5000
        assert result['avg_tokens_per_conversation'] == 500.0
        assert result['whatsapp_conversations'] == 8
        assert result['web_conversations'] == 2


# ============================================
# TESTS PARA cleanup_conversations.py
# ============================================

class TestCleanupConversations:
    """Tests para el job de limpieza de conversaciones"""
    
    def test_get_conversations_to_delete(self):
        """Test: Obtiene conversaciones a eliminar"""
        with patch('scripts.jobs.cleanup_conversations.db') as mock_db:
            mock_db.client.table.return_value.select.return_value.lt.return_value.execute.return_value.data = [
                {'id': '1'}, {'id': '2'}
            ]
            
            from scripts.jobs.cleanup_conversations import get_conversations_to_delete
            
            result = get_conversations_to_delete('2025-01-01')
            
            assert len(result) == 2
            assert '1' in result
    
    def test_delete_messages_returns_zero_for_empty(self):
        """Test: Retorna 0 para lista vacía"""
        from scripts.jobs.cleanup_conversations import delete_messages_for_conversations
        
        result = delete_messages_for_conversations([])
        
        assert result == 0
    
    def test_delete_conversations_returns_zero_for_empty(self):
        """Test: Retorna 0 para lista vacía"""
        from scripts.jobs.cleanup_conversations import delete_conversations
        
        result = delete_conversations([])
        
        assert result == 0


# ============================================
# TESTS PARA cleanup_metrics.py
# ============================================

class TestCleanupMetrics:
    """Tests para el job de limpieza de métricas"""
    
    def test_metrics_tables_defined(self):
        """Test: Tablas de métricas definidas"""
        from scripts.jobs.cleanup_metrics import METRICS_TABLES
        
        assert 'conversation_metrics' in METRICS_TABLES
        assert 'intent_metrics' in METRICS_TABLES
        assert 'product_metrics' in METRICS_TABLES
        assert 'performance_metrics' in METRICS_TABLES
        assert len(METRICS_TABLES) == 4
    
    def test_get_metrics_to_delete(self):
        """Test: Obtiene métricas a eliminar"""
        with patch('scripts.jobs.cleanup_metrics.db') as mock_db:
            mock_db.client.table.return_value.select.return_value.lt.return_value.execute.return_value.data = [
                {'id': '1'}, {'id': '2'}, {'id': '3'}
            ]
            
            from scripts.jobs.cleanup_metrics import get_metrics_to_delete
            
            result = get_metrics_to_delete('conversation_metrics', '2025-01-01')
            
            assert len(result) == 3
    
    def test_delete_metrics_returns_zero_for_empty(self):
        """Test: Retorna 0 para lista vacía"""
        from scripts.jobs.cleanup_metrics import delete_metrics
        
        result = delete_metrics('conversation_metrics', [])
        
        assert result == 0


# ============================================
# TESTS DE INTEGRACIÓN
# ============================================

class TestJobsIntegration:
    """Tests de integración para los jobs"""
    
    def test_calculate_metrics_job_execution(self):
        """Test: Job de cálculo ejecuta sin errores"""
        with patch('scripts.jobs.calculate_metrics.db') as mock_db:
            # Mock tenants
            mock_db.client.table.return_value.select.return_value.execute.return_value.data = [
                {'id': str(uuid4())}
            ]
            
            from scripts.jobs.calculate_metrics import run_daily_metrics_job
            
            # No debe lanzar excepción
            try:
                run_daily_metrics_job(date.today() - timedelta(days=1))
            except Exception as e:
                pytest.fail(f"Job execution failed: {e}")
    
    def test_cleanup_old_conversations_dry_run(self):
        """Test: Cleanup en modo dry-run no elimina"""
        with patch('scripts.jobs.cleanup_conversations.db') as mock_db:
            from scripts.jobs.cleanup_conversations import cleanup_old_conversations
            
            # No debe lanzar excepción
            try:
                cleanup_old_conversations(days=90, dry_run=True)
            except Exception as e:
                pytest.fail(f"Dry run failed: {e}")
    
    def test_cleanup_old_metrics_dry_run(self):
        """Test: Cleanup métricas en modo dry-run"""
        with patch('scripts.jobs.cleanup_metrics.db') as mock_db:
            from scripts.jobs.cleanup_metrics import cleanup_old_metrics
            
            # No debe lanzar excepción
            try:
                cleanup_old_metrics(days=365, dry_run=True)
            except Exception as e:
                pytest.fail(f"Dry run failed: {e}")


# ============================================
# EJECUCIÓN
# ============================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
