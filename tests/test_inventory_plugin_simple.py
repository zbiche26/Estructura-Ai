"""Tests del Inventory Plugin (versión simple) """

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from src.plugins.inventory.plugin import InventoryPlugin
from src.core.event_bus import EventBus


@pytest.fixture
def mock_event_bus():
    """Mock del event bus"""
    return Mock(spec=EventBus)


@pytest.fixture
def mock_db_client():
    """Mock del cliente de base de datos"""
    return Mock()


@pytest.fixture
def plugin(mock_event_bus, mock_db_client):
    """Fixture del plugin"""
    return InventoryPlugin(mock_event_bus, mock_db_client)


def test_plugin_init(plugin):
    """Test 1: Inicialización"""
    assert plugin.name == "inventory_plugin"
    assert plugin.version == "1.0.0"
    assert plugin.stock_manager is None


def test_plugin_initialize(plugin):
    """Test 2: Plugin se inicializa"""
    result = plugin.initialize()
    assert result is True
    assert plugin.stock_manager is not None


def test_plugin_info(plugin):
    """Test 3: Info del plugin"""
    assert plugin.name == 'inventory_plugin'
    assert plugin.version == '1.0.0'


def test_plugin_starts_stopped(plugin):
    """Test 4: Inicia en estado detenido"""
    assert plugin._running is False


def test_plugin_becomes_running(plugin):
    """Test 5: Estado running después de start"""
    plugin.initialize()
    plugin.start()
    assert plugin._running is True


def test_plugin_stops(plugin):
    """Test 6: Se puede detener"""
    plugin.initialize()
    plugin.start()
    plugin.stop()
    assert plugin._running is False


def test_plugin_with_db_client(plugin, mock_db_client):
    """Test 7: Guarda el cliente de DB"""
    assert plugin.db_client == mock_db_client


def test_plugin_has_event_bus(plugin, mock_event_bus):
    """Test 8: Tiene acceso al event bus"""
    assert plugin.event_bus == mock_event_bus
