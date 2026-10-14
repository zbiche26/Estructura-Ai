"""
Tests para Inventory Reports Service

"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timedelta

from src.services.inventory_reports import InventoryReportService


@pytest.fixture
def report_service():
    """Fixture del servicio de reportes"""
    return InventoryReportService()


def test_report_service_init(report_service):
    """Test: Servicio se inicializa correctamente"""
    assert report_service is not None
    assert report_service.supabase is not None


def test_classify_rotation_high(report_service):
    """Test: Clasificación de rotación alta"""
    result = report_service._classify_rotation(100, 2.5)
    assert result == 'high_rotation'


def test_classify_rotation_medium(report_service):
    """Test: Clasificación de rotación media"""
    result = report_service._classify_rotation(50, 1.0)
    assert result == 'medium_rotation'


def test_classify_rotation_low(report_service):
    """Test: Clasificación de rotación baja"""
    result = report_service._classify_rotation(10, 0.3)
    assert result == 'low_rotation'


def test_classify_rotation_no_movement(report_service):
    """Test: Clasificación sin movimiento"""
    result = report_service._classify_rotation(0, 0)
    assert result == 'no_movement'


def test_calculate_risk_level_high(report_service):
    """Test: Nivel de riesgo alto"""
    result = report_service._calculate_risk_level(100, 50)
    assert result == 'high'


def test_calculate_risk_level_medium(report_service):
    """Test: Nivel de riesgo medio"""
    result = report_service._calculate_risk_level(70, 20)
    assert result == 'medium'


def test_calculate_risk_level_low(report_service):
    """Test: Nivel de riesgo bajo"""
    result = report_service._calculate_risk_level(35, 10)
    assert result == 'low'


def test_calculate_risk_level_none(report_service):
    """Test: Sin nivel de riesgo"""
    result = report_service._calculate_risk_level(20, 5)
    assert result == 'none'


def test_get_product_rotation_with_mock(report_service):
    """Test: Obtener rotación de productos con mock"""
    # Crear mock del supabase con la función correcta
    mock_rpc_call = MagicMock()
    mock_rpc_call.execute.return_value.data = [
        {
            'id': str(uuid4()),
            'name': 'Producto 1',
            'category': 'Electronics',
            'current_stock': 100,
            'units_sold': 50,
            'avg_sale_quantity': 2.5,
            'rotation_rate': 0.5
        }
    ]
    
    # Configurar que rpc devuelva el mock cuando se llame con 'get_product_rotation'
    report_service.supabase.rpc = MagicMock(return_value=mock_rpc_call)
    
    result = report_service.get_product_rotation('demo', 30)
    
    assert isinstance(result, list)
    # Verificar que se llamaron los métodos del mock
    assert report_service.supabase.rpc.called


def test_get_stale_products_with_mock(report_service):
    """Test: Obtener productos sin movimiento con mock"""
    mock_rpc = MagicMock()
    mock_rpc.execute.return_value.data = [
        {
            'id': str(uuid4()),
            'name': 'Producto Viejo',
            'category': 'Electronics',
            'stock': 50,
            'last_movement_date': None,
            'days_since_last_movement': 45
        }
    ]
    
    report_service.supabase.rpc = mock_rpc
    
    result = report_service.get_stale_products('demo', 30)
    
    assert isinstance(result, list)


def test_get_stock_adjustments_history_with_mock(report_service):
    """Test: Obtener historial de ajustes con mock"""
    # Mock de la cadena de llamadas
    mock_table = MagicMock()
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_order = MagicMock()
    mock_limit = MagicMock()
    
    mock_select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.eq.return_value = mock_eq
    mock_eq.order.return_value = mock_order
    mock_order.limit.return_value = mock_limit
    mock_limit.execute.return_value.data = [
        {
            'id': str(uuid4()),
            'product_id': str(uuid4()),
            'quantity': 10,
            'stock_before': 90,
            'stock_after': 100,
            'reason': 'Reposición',
            'notes': None,
            'user_id': str(uuid4()),
            'created_at': datetime.now().isoformat()
        }
    ]
    
    report_service.supabase.table = mock_table
    mock_table.return_value = mock_table
    
    result = report_service.get_stock_adjustments_history(tenant_id='demo')
    
    assert isinstance(result, list)
