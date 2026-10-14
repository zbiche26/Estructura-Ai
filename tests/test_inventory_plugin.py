import pytest
from unittest.mock import Mock
from src.plugins.inventory.plugin import InventoryPlugin
from src.plugins.base import PluginStatus
from src.core.event_bus import EventBus


@pytest.fixture
def mock_event_bus():
    return Mock(spec=EventBus)

@pytest.fixture
def mock_db_client():
    return Mock()

@pytest.fixture
def plugin(mock_event_bus, mock_db_client):
    return InventoryPlugin(mock_event_bus, mock_db_client)


def test_plugin_metadata(plugin):
    # Acepta cualquier nombre válido del plugin
    assert plugin.name is not None
    assert len(plugin.name) > 0
    assert plugin.version is not None
    assert plugin.description is not None

def test_plugin_init(plugin, mock_event_bus, mock_db_client):
    assert plugin.stock_manager is None
    assert plugin._running is False
    assert plugin.db_client == mock_db_client

def test_plugin_initialize(plugin):
    result = plugin.initialize()
    assert result is True
    assert plugin.stock_manager is not None
    assert plugin.status == PluginStatus.INITIALIZED

def test_plugin_start(plugin):
    plugin.initialize()
    result = plugin.start()
    assert result is True
    assert plugin.status == PluginStatus.RUNNING
    assert plugin._running is True

def test_plugin_stop(plugin):
    plugin.initialize()
    plugin.start()
    result = plugin.stop()
    assert result is True
    assert plugin.status == PluginStatus.STOPPED
    assert plugin._running is False

def test_plugin_lifecycle(plugin):
    assert plugin.status == PluginStatus.UNINITIALIZED
    assert plugin.initialize() is True
    assert plugin.status == PluginStatus.INITIALIZED
    assert plugin.start() is True
    assert plugin.status == PluginStatus.RUNNING
    assert plugin.stop() is True
    assert plugin.status == PluginStatus.STOPPED

def test_plugin_public_methods(plugin):
    plugin.initialize()
    assert hasattr(plugin, "get_stock_manager")
    assert callable(plugin.get_stock_manager)

def test_get_stock_manager(plugin):
    plugin.initialize()
    manager = plugin.get_stock_manager()
    assert manager is not None

def test_event_subscriptions(plugin):
    plugin.initialize()
    plugin.start()
    assert plugin.event_bus.subscribe.call_count >= 2

def test_get_stock_manager_not_initialized(plugin):
    with pytest.raises(RuntimeError, match="StockManager no inicializado"):
        plugin.get_stock_manager()

def test_plugin_metadata_instance(plugin):
    from src.plugins.base import PluginMetadata
    plugin.initialize()
    assert isinstance(plugin.metadata, PluginMetadata)

def test_plugin_running_property(plugin):
    assert plugin.is_running is False
    plugin.initialize()
    plugin.start()
    assert plugin.is_running is True
    plugin.stop()
    assert plugin.is_running is False

def test_plugin_config(plugin):
    plugin.set_config("test_key", "test_value")
    assert plugin.get_config("test_key") == "test_value"
    assert plugin.get_config("non_existent", "default") == "default"

def test_plugin_event_bus_access(plugin):
    assert plugin.event_bus is not None

def test_plugin_repr(plugin):
    plugin.initialize()
    repr_str = repr(plugin)
    assert "inventory" in repr_str.lower() or "plugin" in repr_str.lower()