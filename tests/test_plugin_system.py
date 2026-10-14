"""
test_plugin_system.py - Tests para el Sistema de Plugins 
==============================================================================
Cubre:
  - Registro y validación de plugins
  - Prevención de duplicados
  - Ciclo de vida: carga, habilitación, deshabilitación, descarga
  - Comunicación por eventos entre plugins
  - Manejo de errores y estados de fallo
  - Thread-safety básico
  - KernelManager como fachada

Ejecutar: pytest tests/test_plugin_system.py -v
"""

import threading
import time
import pytest

from src.core.plugin_system import (
    KernelManager,
    PluginEntry,
    PluginEventBus,
    PluginInfo,
    PluginInterface,
    PluginLoader,
    PluginRegistry,
    PluginStatus,
)


# ============================================================
# Fixtures y helpers
# ============================================================

class SimplePlugin(PluginInterface):
    """Plugin mínimo para testing."""

    def __init__(self):
        self.initialized = False
        self.enabled      = False
        self.disabled_count = 0

    def initialize(self) -> None:
        self.initialized = True

    def on_enable(self) -> None:
        self.enabled = True

    def on_disable(self) -> None:
        self.enabled = False
        self.disabled_count += 1

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="simple_plugin",
            version="1.0.0",
            author="Test",
            description="Plugin de prueba",
        )


class FaultyInitPlugin(PluginInterface):
    """Plugin que falla en initialize()."""

    def initialize(self) -> None:
        raise RuntimeError("Error intencional en initialize")

    def on_enable(self) -> None: ...
    def on_disable(self) -> None: ...

    def get_info(self) -> PluginInfo:
        return PluginInfo("faulty_init", "1.0.0", "Test", "Falla en init")


class FaultyEnablePlugin(PluginInterface):
    """Plugin que falla en on_enable()."""

    def initialize(self) -> None: ...

    def on_enable(self) -> None:
        raise RuntimeError("Error intencional en on_enable")

    def on_disable(self) -> None: ...

    def get_info(self) -> PluginInfo:
        return PluginInfo("faulty_enable", "1.0.0", "Test", "Falla en enable")


@pytest.fixture
def registry() -> PluginRegistry:
    return PluginRegistry()


@pytest.fixture
def loader(registry: PluginRegistry) -> PluginLoader:
    return PluginLoader(registry)


@pytest.fixture
def kernel() -> KernelManager:
    return KernelManager()


@pytest.fixture
def event_bus() -> PluginEventBus:
    return PluginEventBus()


# ============================================================
# Grupo 1: PluginRegistry
# ============================================================

class TestPluginRegistry:

    def test_registrar_plugin_exitoso(self, registry):
        """Registrar un plugin válido devuelve PluginInfo."""
        info = registry.register("simple", SimplePlugin)
        assert isinstance(info, PluginInfo)
        assert info.name == "simple_plugin"

    def test_plugin_existe_despues_de_registrar(self, registry):
        """El registry confirma la existencia del plugin."""
        registry.register("simple", SimplePlugin)
        assert registry.exists("simple")

    def test_no_duplicados(self, registry):
        """Registrar dos veces el mismo nombre lanza ValueError."""
        registry.register("simple", SimplePlugin)
        with pytest.raises(ValueError, match="ya registrado"):
            registry.register("simple", SimplePlugin)

    def test_clase_invalida_lanza_typeerror(self, registry):
        """Una clase que no extiende PluginInterface lanza TypeError."""
        class NotAPlugin:
            pass

        with pytest.raises(TypeError):
            registry.register("invalid", NotAPlugin)  # type: ignore

    def test_listar_nombres(self, registry):
        """list_names retorna los nombres registrados."""
        registry.register("a", SimplePlugin)
        registry.register("b", SimplePlugin)  # distinto nombre, misma clase
        assert set(registry.list_names()) == {"a", "b"}

    def test_count(self, registry):
        """count() retorna el número correcto de plugins."""
        assert registry.count() == 0
        registry.register("p1", SimplePlugin)
        assert registry.count() == 1

    def test_desregistrar_plugin(self, registry):
        """Un plugin REGISTERED puede eliminarse del catálogo."""
        registry.register("simple", SimplePlugin)
        result = registry.unregister("simple")
        assert result is True
        assert not registry.exists("simple")

    def test_desregistrar_inexistente_devuelve_false(self, registry):
        """Desregistrar un nombre desconocido retorna False sin excepción."""
        assert registry.unregister("nope") is False

    def test_get_or_raise_lanza_key_error(self, registry):
        """get_or_raise lanza KeyError para plugins no existentes."""
        with pytest.raises(KeyError):
            registry.get_or_raise("no_existe")


# ============================================================
# Grupo 2: PluginLoader — ciclo de vida
# ============================================================

class TestPluginLoader:

    def test_load_ejecuta_initialize(self, registry, loader):
        """load() crea la instancia y llama initialize()."""
        registry.register("simple", SimplePlugin)
        instance = loader.load("simple")
        assert isinstance(instance, SimplePlugin)
        assert instance.initialized is True

    def test_estado_loaded_despues_de_load(self, registry, loader):
        """Después de load() el estado es LOADED."""
        registry.register("simple", SimplePlugin)
        loader.load("simple")
        assert registry.get("simple").status == PluginStatus.LOADED

    def test_enable_llama_on_enable(self, registry, loader):
        """enable() cambia el estado a ENABLED y llama on_enable()."""
        registry.register("simple", SimplePlugin)
        instance = loader.load("simple")
        loader.enable("simple")
        assert instance.enabled is True
        assert registry.get("simple").status == PluginStatus.ENABLED

    def test_disable_llama_on_disable(self, registry, loader):
        """disable() cambia el estado a DISABLED y llama on_disable()."""
        registry.register("simple", SimplePlugin)
        loader.load("simple")
        instance = loader.enable("simple")
        loader.disable("simple")
        assert instance.enabled is False
        assert instance.disabled_count == 1
        assert registry.get("simple").status == PluginStatus.DISABLED

    def test_enable_auto_carga_si_no_esta_loaded(self, registry, loader):
        """enable() carga automáticamente si el plugin no ha sido cargado."""
        registry.register("simple", SimplePlugin)
        instance = loader.enable("simple")   # sin load() previo
        assert instance.initialized is True
        assert instance.enabled is True

    def test_load_plugin_con_error_estado_error(self, registry, loader):
        """Un plugin que falla en initialize() queda en estado ERROR."""
        registry.register("faulty", FaultyInitPlugin)
        with pytest.raises(RuntimeError):
            loader.load("faulty")
        assert registry.get("faulty").status == PluginStatus.ERROR

    def test_enable_plugin_con_error_estado_error(self, registry, loader):
        """Un plugin que falla en on_enable() queda en estado ERROR."""
        registry.register("faulty_e", FaultyEnablePlugin)
        loader.load("faulty_e")
        with pytest.raises(RuntimeError):
            loader.enable("faulty_e")
        assert registry.get("faulty_e").status == PluginStatus.ERROR

    def test_is_enabled_verdadero(self, registry, loader):
        """is_enabled() retorna True solo cuando el plugin está ENABLED."""
        registry.register("simple", SimplePlugin)
        loader.load("simple")
        assert not loader.is_enabled("simple")
        loader.enable("simple")
        assert loader.is_enabled("simple")


# ============================================================
# Grupo 3: PluginEventBus
# ============================================================

class TestPluginEventBus:

    def test_handler_recibe_payload(self, event_bus):
        """El handler recibe el payload correcto del evento."""
        recibido = []
        event_bus.subscribe("test.evento", lambda data: recibido.append(data))
        event_bus.publish("test.evento", {"valor": 42})
        assert recibido == [{"valor": 42}]

    def test_multiples_handlers_notificados(self, event_bus):
        """Varios handlers suscritos al mismo evento son notificados."""
        contador = []
        for _ in range(3):
            event_bus.subscribe("test.multi", lambda d: contador.append(1))
        event_bus.publish("test.multi", None)
        assert len(contador) == 3

    def test_sin_suscriptores_devuelve_cero(self, event_bus):
        """Publicar sin suscriptores retorna 0 handlers notificados."""
        result = event_bus.publish("evento.huerfano")
        assert result == 0

    def test_historial_registra_eventos(self, event_bus):
        """El historial guarda los eventos publicados."""
        event_bus.publish("ev.a", {"n": 1})
        event_bus.publish("ev.a", {"n": 2})
        historial = event_bus.get_history("ev.a")
        assert len(historial) == 2
        assert historial[0]["data"]["n"] == 1

    def test_desuscribirse_detiene_notificaciones(self, event_bus):
        """Un handler desuscrito deja de recibir eventos."""
        recibido = []
        handler = lambda data: recibido.append(data)
        event_bus.subscribe("ev.des", handler)
        event_bus.publish("ev.des", 1)
        event_bus.unsubscribe("ev.des", handler)
        event_bus.publish("ev.des", 2)
        assert recibido == [1]   # solo el primer publish

    def test_handler_con_error_no_detiene_otros(self, event_bus):
        """Un handler que lanza excepción no interrumpe a los demás."""
        ok = []

        def handler_malo(data):
            raise ValueError("fallo intencional")

        def handler_bueno(data):
            ok.append(data)

        event_bus.subscribe("ev.err", handler_malo)
        event_bus.subscribe("ev.err", handler_bueno)
        event_bus.publish("ev.err", "payload")
        assert ok == ["payload"]


# ============================================================
# Grupo 4: KernelManager (fachada)
# ============================================================

class TestKernelManager:

    def test_start_plugin_habilita_instancia(self, kernel):
        """start_plugin registra, carga y habilita el plugin."""
        kernel.register_plugin("simple", SimplePlugin)
        instance = kernel.start_plugin("simple")
        assert isinstance(instance, SimplePlugin)
        assert kernel.is_plugin_active("simple")

    def test_stop_plugin_desactiva_y_descarga(self, kernel):
        """stop_plugin deshabilita y descarga el plugin."""
        kernel.register_plugin("simple", SimplePlugin)
        kernel.start_plugin("simple")
        kernel.stop_plugin("simple")
        assert not kernel.is_plugin_active("simple")
        assert kernel.registry.get("simple").status == PluginStatus.REGISTERED

    def test_status_report_muestra_todos(self, kernel):
        """status_report incluye todos los plugins con sus estados."""
        kernel.register_plugin("a", SimplePlugin)
        kernel.register_plugin("b", SimplePlugin)
        kernel.start_plugin("a")
        report = kernel.status_report()
        assert "a" in report
        assert "b" in report
        assert report["a"] == "ENABLED"
        assert report["b"] == "REGISTERED"

    def test_active_plugins_lista_habilitados(self, kernel):
        """active_plugins() solo incluye los plugins en ENABLED."""
        kernel.register_plugin("x", SimplePlugin)
        kernel.register_plugin("y", SimplePlugin)
        kernel.start_plugin("x")
        activos = kernel.active_plugins()
        assert "x" in activos
        assert "y" not in activos


# ============================================================
# Grupo 5: Thread-safety
# ============================================================

class TestThreadSafety:

    def test_registro_concurrente_sin_duplicados(self):
        """
        Muchos hilos registrando plugins diferentes
        no deben generar condiciones de carrera.
        """
        registry = PluginRegistry()
        errores = []

        def registrar(n):
            try:
                registry.register(f"plugin_{n}", SimplePlugin)
            except Exception as e:
                errores.append(e)

        hilos = [threading.Thread(target=registrar, args=(i,)) for i in range(20)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()

        # No deben existir errores (cada nombre es único)
        assert errores == []
        assert registry.count() == 20