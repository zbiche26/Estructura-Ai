"""
Tests para el Sistema de Plugins
"""
import pytest
from typing import Dict, Any

from src.core.event_bus import EventBus
from src.plugins import (
    BasePlugin,
    PluginMetadata,
    PluginStatus,
    PluginRegistry,
    PluginManager,
    register_plugin,
    require_running,
    log_execution,
    measure_time,
    validate_config
)


# ==================== PLUGINS DE PRUEBA ====================

class DummyPlugin(BasePlugin):
    """Plugin de prueba simple"""
    
    def __init__(self, event_bus, tenant_context=None):
        super().__init__(event_bus, tenant_context)
        self._metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Plugin de prueba",
            author="Test"
        )
        self.initialized = False
        self.started = False
        self.stopped = False
    
    def on_initialize(self):
        self.initialized = True
    
    def on_start(self):
        self.started = True
    
    def on_stop(self):
        self.stopped = True
    
    @require_running
    def process(self, data: str) -> str:
        return f"processed: {data}"


class DependentPlugin(BasePlugin):
    """Plugin con dependencias"""
    
    def __init__(self, event_bus, tenant_context=None):
        super().__init__(event_bus, tenant_context)
        self._metadata = PluginMetadata(
            name="dependent",
            version="1.0.0",
            description="Plugin dependiente",
            dependencies=["dummy"]
        )
    
    def on_initialize(self):
        pass
    
    def on_start(self):
        pass
    
    def on_stop(self):
        pass


class ConfigurablePlugin(BasePlugin):
    """Plugin con configuración"""
    
    def __init__(self, event_bus, tenant_context=None):
        super().__init__(event_bus, tenant_context)
        self._metadata = PluginMetadata(
            name="configurable",
            version="1.0.0",
            description="Plugin configurable"
        )
    
    def on_initialize(self):
        # Validar configuración
        required = ["api_key", "endpoint"]
        for key in required:
            if key not in self.config:
                raise ValueError(f"Falta config: {key}")
    
    def on_start(self):
        pass
    
    def on_stop(self):
        pass
    
    @validate_config("api_key", "endpoint")
    def connect(self) -> bool:
        return True


# ==================== FIXTURES ====================

@pytest.fixture
def event_bus():
    """Event bus limpio"""
    return EventBus()


@pytest.fixture
def registry():
    """Registry limpio"""
    reg = PluginRegistry()
    reg.clear()
    return reg


@pytest.fixture
def manager(event_bus, registry):
    """Manager limpio"""
    return PluginManager(event_bus, registry)


# ==================== TESTS: BASE PLUGIN ====================

class TestBasePlugin:
    """Tests para BasePlugin"""
    
    def test_plugin_creation(self, event_bus):
        """Verifica creación básica"""
        plugin = DummyPlugin(event_bus)
        
        assert plugin.metadata.name == "dummy"
        assert plugin.status == PluginStatus.UNINITIALIZED
        assert not plugin.is_running
        assert plugin.error is None
    
    def test_plugin_initialization(self, event_bus):
        """Verifica inicialización"""
        plugin = DummyPlugin(event_bus)
        
        success = plugin.initialize()
        
        assert success
        assert plugin.status == PluginStatus.INITIALIZED
        assert plugin.initialized
    
    def test_plugin_start(self, event_bus):
        """Verifica inicio"""
        plugin = DummyPlugin(event_bus)
        plugin.initialize()
        
        success = plugin.start()
        
        assert success
        assert plugin.status == PluginStatus.RUNNING
        assert plugin.is_running
        assert plugin.started
    
    def test_plugin_stop(self, event_bus):
        """Verifica detención"""
        plugin = DummyPlugin(event_bus)
        plugin.initialize()
        plugin.start()
        
        success = plugin.stop()
        
        assert success
        assert plugin.status == PluginStatus.STOPPED
        assert not plugin.is_running
        assert plugin.stopped
    
    def test_plugin_lifecycle_order(self, event_bus):
        """Verifica orden correcto del ciclo de vida"""
        plugin = DummyPlugin(event_bus)
        
        # No se puede iniciar sin inicializar
        assert not plugin.start()
        
        # Inicializar
        assert plugin.initialize()
        
        # No se puede detener sin iniciar
        assert not plugin.stop()
        
        # Iniciar y detener
        assert plugin.start()
        assert plugin.stop()
    
    def test_plugin_config(self, event_bus):
        """Verifica configuración"""
        plugin = DummyPlugin(event_bus)
        config = {"key1": "value1", "key2": 42}
        
        plugin.initialize(config)
        
        assert plugin.get_config("key1") == "value1"
        assert plugin.get_config("key2") == 42
        assert plugin.get_config("missing", "default") == "default"
    
    def test_plugin_events(self, event_bus):
        """Verifica emisión de eventos"""
        events = []
        event_bus.subscribe("plugin.initialized", lambda e: events.append(e))
        event_bus.subscribe("plugin.started", lambda e: events.append(e))
        
        plugin = DummyPlugin(event_bus)
        plugin.initialize()
        plugin.start()
        
        # Verificar que se emitieron 2 eventos
        assert len(events) == 2, "Deberían haberse emitido 2 eventos"
        
        # Verificar que ambos eventos son objetos válidos (no None)
        assert events[0] is not None, "El primer evento no debería ser None"
        assert events[1] is not None, "El segundo evento no debería ser None"
    
    def test_require_running_decorator(self, event_bus):
        """Verifica decorador @require_running"""
        plugin = DummyPlugin(event_bus)
        plugin.initialize()
        
        # Falla si no está corriendo
        with pytest.raises(RuntimeError):
            plugin.process("test")
        
        # Funciona si está corriendo
        plugin.start()
        result = plugin.process("test")
        assert result == "processed: test"


# ==================== TESTS: REGISTRY ====================

class TestPluginRegistry:
    """Tests para PluginRegistry"""
    
    def test_singleton(self):
        """Verifica que Registry es singleton"""
        reg1 = PluginRegistry()
        reg2 = PluginRegistry()
        
        assert reg1 is reg2
    
    def test_register_plugin(self, registry):
        """Verifica registro de plugin"""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test plugin"
        )
        
        registry.register(DummyPlugin, metadata)
        
        assert registry.is_registered("test")
        assert "test" in registry.list_plugins()
    
    def test_register_duplicate(self, registry):
        """Verifica que no se puede registrar duplicados"""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test"
        )
        
        registry.register(DummyPlugin, metadata)
        
        with pytest.raises(ValueError):
            registry.register(DummyPlugin, metadata)
    
    def test_unregister_plugin(self, registry):
        """Verifica desregistro"""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test"
        )
        
        registry.register(DummyPlugin, metadata)
        registry.unregister("test")
        
        assert not registry.is_registered("test")
    
    def test_get_plugin_class(self, registry):
        """Verifica obtención de clase"""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="Test"
        )
        
        registry.register(DummyPlugin, metadata)
        plugin_class = registry.get_plugin_class("test")
        
        assert plugin_class == DummyPlugin
    
    def test_dependencies(self, registry):
        """Verifica manejo de dependencias"""
        # Registrar dummy
        dummy_meta = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, dummy_meta)
        
        # Registrar dependiente
        dep_meta = PluginMetadata(
            name="dependent",
            version="1.0.0",
            description="Dependent",
            dependencies=["dummy"]
        )
        registry.register(DependentPlugin, dep_meta)
        
        # Verificar dependencias
        deps = registry.get_dependencies("dependent")
        assert "dummy" in deps
        assert registry.check_dependencies("dependent")
    
    def test_load_order(self, registry):
        """Verifica orden de carga correcto"""
        # Registrar plugins con dependencias
        dummy_meta = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, dummy_meta)
        
        dep_meta = PluginMetadata(
            name="dependent",
            version="1.0.0",
            description="Dependent",
            dependencies=["dummy"]
        )
        registry.register(DependentPlugin, dep_meta)
        
        # Verificar orden
        order = registry.get_load_order()
        
        assert order.index("dummy") < order.index("dependent")


# ==================== TESTS: MANAGER ====================

class TestPluginManager:
    """Tests para PluginManager"""
    
    def test_initialize_plugin(self, manager, registry):
        """Verifica inicialización de plugin"""
        metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, metadata)
        
        success = manager.initialize_plugin("dummy")
        
        assert success
        assert "dummy" in manager.list_active_plugins()
    
    def test_start_plugin(self, manager, registry):
        """Verifica inicio de plugin"""
        metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, metadata)
        
        manager.initialize_plugin("dummy")
        success = manager.start_plugin("dummy")
        
        assert success
        assert manager.is_plugin_running("dummy")
    
    def test_stop_plugin(self, manager, registry):
        """Verifica detención de plugin"""
        metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, metadata)
        
        manager.initialize_plugin("dummy")
        manager.start_plugin("dummy")
        success = manager.stop_plugin("dummy")
        
        assert success
        assert not manager.is_plugin_running("dummy")
        assert "dummy" not in manager.list_active_plugins()
    
    def test_initialize_all(self, manager, registry):
        """Verifica inicialización de todos los plugins"""
        # Registrar múltiples plugins
        dummy_meta = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, dummy_meta)
        
        dep_meta = PluginMetadata(
            name="dependent",
            version="1.0.0",
            description="Dependent",
            dependencies=["dummy"]
        )
        registry.register(DependentPlugin, dep_meta)
        
        # Inicializar todos
        results = manager.initialize_all()
        
        assert results["dummy"]
        assert results["dependent"]
        assert len(manager.list_active_plugins()) == 2
    
    def test_health_check(self, manager, registry):
        """Verifica health check"""
        metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, metadata)
        
        manager.initialize_plugin("dummy")
        manager.start_plugin("dummy")
        
        health = manager.health_check()
        
        assert "dummy" in health
        assert health["dummy"]["is_running"]
        assert health["dummy"]["status"] == "running"
    
    def test_plugin_with_config(self, manager, registry):
        """Verifica plugin con configuración"""
        metadata = PluginMetadata(
            name="configurable",
            version="1.0.0",
            description="Configurable"
        )
        registry.register(ConfigurablePlugin, metadata)
        
        # Sin config falla
        assert not manager.initialize_plugin("configurable")
        
        # Con config funciona
        config = {
            "api_key": "test_key",
            "endpoint": "https://api.test.com"
        }
        assert manager.initialize_plugin("configurable", config)
    
    def test_reload_plugin(self, manager, registry):
        """Verifica recarga de plugin"""
        metadata = PluginMetadata(
            name="dummy",
            version="1.0.0",
            description="Dummy"
        )
        registry.register(DummyPlugin, metadata)
        
        manager.initialize_plugin("dummy")
        manager.start_plugin("dummy")
        
        # Recargar
        success = manager.reload_plugin("dummy")
        
        assert success
        assert manager.is_plugin_running("dummy")


# ==================== TESTS: DECORATORS ====================

class TestDecorators:
    """Tests para decoradores"""
    
    def test_validate_config_decorator(self, event_bus):
        """Verifica decorador @validate_config"""
        plugin = ConfigurablePlugin(event_bus)
        config = {
            "api_key": "test_key",
            "endpoint": "https://api.test.com"
        }
        plugin.initialize(config)
        plugin.start()
        
        # Funciona con config correcta
        assert plugin.connect()
        
        # Falla si falta config
        plugin._config = {"api_key": "test"}
        with pytest.raises(ValueError):
            plugin.connect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])