"""
plugin_system.py - Sistema Base de Plugins (Micro-Kernel)
=========================================================
Implementa el núcleo del patrón Micro-Kernel:
  - PluginRegistry: Catálogo thread-safe de plugins
  - PluginLoader:   Carga dinámica con lifecycle management
  - PluginEventBus: Canal de comunicación entre plugins

Diseño guiado por los patrones del proyecto:
  - Thread-safe  (como TenantContext)
  - Observer     (como EventBus)
  - DI-friendly  (sin singletons hardcodeados)
"""

from __future__ import annotations

import importlib
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Type

from src.core.logger import logger


# ---------------------------------------------------------------------------
# Enums y Value Objects
# ---------------------------------------------------------------------------

class PluginStatus(Enum):
    """Estados del ciclo de vida de un plugin."""
    REGISTERED  = auto()   # En catálogo, sin cargar
    LOADED      = auto()   # Instanciado, no activo
    ENABLED     = auto()   # Activo y operando
    DISABLED    = auto()   # Desactivado (limpieza hecha)
    ERROR       = auto()   # Fallo en alguna fase


@dataclass(frozen=True)
class PluginInfo:
    """
    Value Object con metadatos inmutables de un plugin.
    Se obtiene llamando a plugin.get_info().
    """
    name:        str
    version:     str
    author:      str
    description: str
    dependencies: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class PluginEntry:
    """
    Entrada interna del registry.
    Guarda clase, instancia y estado actual.
    """
    plugin_class:  Type[PluginInterface]
    info:          PluginInfo
    status:        PluginStatus = PluginStatus.REGISTERED
    instance:      Optional[PluginInterface] = None
    error_message: Optional[str] = None
    loaded_at:     Optional[float] = None


# ---------------------------------------------------------------------------
# Interface Base de Plugins
# ---------------------------------------------------------------------------

class PluginInterface(ABC):
    """
    Contrato que todo plugin debe cumplir.
    Define el ciclo de vida completo:
      1. initialize()  → configuración inicial
      2. on_enable()   → activación
      3. on_disable()  → desactivación y limpieza
      4. get_info()    → metadatos

    Uso:
        class MiPlugin(PluginInterface):
            def initialize(self) -> None:
                self._db = conectar_bd()

            def on_enable(self) -> None:
                logger.info("MiPlugin activo")

            def on_disable(self) -> None:
                self._db.close()

            def get_info(self) -> PluginInfo:
                return PluginInfo(
                    name="mi_plugin",
                    version="1.0.0",
                    author="Camilo",
                    description="Ejemplo"
                )
    """

    @abstractmethod
    def initialize(self) -> None:
        """
        Se ejecuta una sola vez al cargar el plugin.
        Úsalo para: conectar BD, crear instancias pesadas, etc.
        """
        ...

    @abstractmethod
    def on_enable(self) -> None:
        """
        Se ejecuta al activar el plugin (puede llamarse varias veces).
        Úsalo para: suscribirse a eventos, abrir conexiones ligeras.
        """
        ...

    @abstractmethod
    def on_disable(self) -> None:
        """
        Se ejecuta al desactivar el plugin.
        Úsalo para: desuscribirse de eventos, liberar recursos.
        """
        ...

    @abstractmethod
    def get_info(self) -> PluginInfo:
        """Retorna los metadatos del plugin."""
        ...


# ---------------------------------------------------------------------------
# Plugin Registry  (Catálogo thread-safe)
# ---------------------------------------------------------------------------

class PluginRegistry:
    """
    Catálogo central de plugins — thread-safe.

    Responsabilidades:
      - Registrar clases de plugins con nombre único
      - Buscar plugins por nombre
      - Listar todos los plugins registrados
      - Validar ausencia de duplicados

    No instancia plugins; eso es responsabilidad de PluginLoader.

    Uso:
        registry = PluginRegistry()
        registry.register("excel_import", ExcelImportPlugin)

        entry = registry.get("excel_import")
        nombres = registry.list_names()
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, PluginEntry] = {}
        self._lock = threading.RLock()
        logger.debug("PluginRegistry inicializado")

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        plugin_class: Type[PluginInterface],
    ) -> PluginInfo:
        """
        Registra un plugin en el catálogo.

        Args:
            name:         Nombre único del plugin (snake_case recomendado).
            plugin_class: Clase que implementa PluginInterface.

        Returns:
            PluginInfo con los metadatos del plugin registrado.

        Raises:
            ValueError: Si ya existe un plugin con ese nombre.
            TypeError:  Si la clase no implementa PluginInterface.
        """
        if not (isinstance(plugin_class, type) and
                issubclass(plugin_class, PluginInterface)):
            raise TypeError(
                f"'{plugin_class}' no implementa PluginInterface"
            )

        with self._lock:
            if name in self._plugins:
                raise ValueError(
                    f"Plugin '{name}' ya registrado. "
                    "Usa un nombre diferente o desregistra el anterior."
                )

            # Instancia temporal solo para leer los metadatos
            try:
                temp = plugin_class.__new__(plugin_class)
                info = temp.get_info()
            except Exception as exc:
                raise ValueError(
                    f"No se pudo obtener info de '{name}': {exc}"
                ) from exc

            entry = PluginEntry(plugin_class=plugin_class, info=info)
            self._plugins[name] = entry

        logger.info(
            f"Plugin registrado: '{name}' "
            f"v{info.version} por {info.author}"
        )
        return info

    def unregister(self, name: str) -> bool:
        """
        Elimina un plugin del catálogo.
        Solo plugins en estado REGISTERED o ERROR pueden eliminarse
        (los activos deben deshabilitarse primero).

        Returns:
            True si se eliminó, False si no existía.
        """
        with self._lock:
            entry = self._plugins.get(name)
            if entry is None:
                logger.warning(f"Intento de desregistrar plugin inexistente: '{name}'")
                return False

            if entry.status == PluginStatus.ENABLED:
                raise RuntimeError(
                    f"No se puede desregistrar '{name}' mientras está ENABLED. "
                    "Deshabilítalo primero."
                )

            del self._plugins[name]

        logger.info(f"Plugin desregistrado: '{name}'")
        return True

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[PluginEntry]:
        """Retorna la entrada del plugin o None si no existe."""
        with self._lock:
            return self._plugins.get(name)

    def get_or_raise(self, name: str) -> PluginEntry:
        """
        Retorna la entrada del plugin.

        Raises:
            KeyError: Si el plugin no está registrado.
        """
        entry = self.get(name)
        if entry is None:
            raise KeyError(f"Plugin '{name}' no registrado")
        return entry

    def list_names(self) -> List[str]:
        """Lista los nombres de todos los plugins registrados."""
        with self._lock:
            return list(self._plugins.keys())

    def list_entries(self) -> List[PluginEntry]:
        """Lista todas las entradas del catálogo."""
        with self._lock:
            return list(self._plugins.values())

    def exists(self, name: str) -> bool:
        """Verifica si un plugin está registrado."""
        with self._lock:
            return name in self._plugins

    def count(self) -> int:
        """Número total de plugins registrados."""
        with self._lock:
            return len(self._plugins)

    # ------------------------------------------------------------------
    # Búsqueda por estado
    # ------------------------------------------------------------------

    def list_by_status(self, status: PluginStatus) -> List[str]:
        """Nombres de plugins con el estado indicado."""
        with self._lock:
            return [
                name
                for name, entry in self._plugins.items()
                if entry.status == status
            ]

    # ------------------------------------------------------------------
    # Actualización interna (usado por PluginLoader)
    # ------------------------------------------------------------------

    def _update_entry(self, name: str, **kwargs: Any) -> None:
        """Actualiza campos de una entrada (uso interno de PluginLoader)."""
        with self._lock:
            entry = self._plugins.get(name)
            if entry is None:
                raise KeyError(f"Plugin '{name}' no encontrado")
            for key, value in kwargs.items():
                setattr(entry, key, value)


# ---------------------------------------------------------------------------
# Plugin Loader  (Carga dinámica + lifecycle)
# ---------------------------------------------------------------------------

class PluginLoader:
    """
    Gestiona el ciclo de vida completo de los plugins:
      REGISTERED → LOADED → ENABLED → DISABLED

    Trabaja sobre un PluginRegistry compartido.

    Uso:
        registry = PluginRegistry()
        registry.register("excel_import", ExcelImportPlugin)

        loader = PluginLoader(registry)
        loader.load("excel_import")
        loader.enable("excel_import")
        # ... usar plugin ...
        loader.disable("excel_import")
    """

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry
        self._lock = threading.RLock()
        logger.debug("PluginLoader inicializado")

    # ------------------------------------------------------------------
    # Carga / descarga
    # ------------------------------------------------------------------

    def load(self, name: str, **init_kwargs: Any) -> PluginInterface:
        """
        Instancia el plugin y ejecuta initialize().

        Args:
            name:        Nombre del plugin registrado.
            init_kwargs: Argumentos opcionales para el constructor.

        Returns:
            Instancia inicializada del plugin.
        """
        entry = self._registry.get_or_raise(name)

        if entry.status not in (PluginStatus.REGISTERED, PluginStatus.ERROR):
            logger.debug(
                f"Plugin '{name}' ya está en estado {entry.status.name}, "
                "saltando carga"
            )
            return entry.instance  # type: ignore[return-value]

        logger.info(f"Cargando plugin '{name}'...")
        try:
            instance = entry.plugin_class(**init_kwargs)
            instance.initialize()

            self._registry._update_entry(
                name,
                instance=instance,
                status=PluginStatus.LOADED,
                loaded_at=time.time(),
                error_message=None,
            )
            logger.success(f"Plugin '{name}' cargado correctamente")
            return instance

        except Exception as exc:
            self._registry._update_entry(
                name,
                status=PluginStatus.ERROR,
                error_message=str(exc),
            )
            logger.error(f"Error al cargar plugin '{name}': {exc}")
            raise RuntimeError(f"Fallo al cargar '{name}'") from exc

    def unload(self, name: str) -> None:
        """
        Descarga el plugin (lo regresa a estado REGISTERED).
        El plugin debe estar en DISABLED o LOADED.
        """
        entry = self._registry.get_or_raise(name)

        if entry.status == PluginStatus.ENABLED:
            raise RuntimeError(
                f"Plugin '{name}' está ENABLED. Deshabilítalo antes de descargar."
            )

        self._registry._update_entry(
            name,
            instance=None,
            status=PluginStatus.REGISTERED,
            loaded_at=None,
            error_message=None,
        )
        logger.info(f"Plugin '{name}' descargado")

    # ------------------------------------------------------------------
    # Habilitación / deshabilitación
    # ------------------------------------------------------------------

    def enable(self, name: str) -> PluginInterface:
        """
        Activa un plugin cargado ejecutando on_enable().
        Si no está cargado, lo carga primero.

        Returns:
            Instancia activa del plugin.
        """
        entry = self._registry.get_or_raise(name)

        if entry.status == PluginStatus.ENABLED:
            logger.debug(f"Plugin '{name}' ya está habilitado")
            return entry.instance  # type: ignore[return-value]

        if entry.status not in (PluginStatus.LOADED, PluginStatus.DISABLED):
            # Auto-cargar si es necesario
            self.load(name)
            entry = self._registry.get_or_raise(name)

        logger.info(f"Habilitando plugin '{name}'...")
        try:
            entry.instance.on_enable()  # type: ignore[union-attr]
            self._registry._update_entry(name, status=PluginStatus.ENABLED)
            logger.success(f"Plugin '{name}' habilitado")
            return entry.instance  # type: ignore[return-value]

        except Exception as exc:
            self._registry._update_entry(
                name, status=PluginStatus.ERROR, error_message=str(exc)
            )
            logger.error(f"Error al habilitar '{name}': {exc}")
            raise RuntimeError(f"Fallo al habilitar '{name}'") from exc

    def disable(self, name: str) -> None:
        """
        Desactiva un plugin ejecutando on_disable().
        """
        entry = self._registry.get_or_raise(name)

        if entry.status != PluginStatus.ENABLED:
            logger.warning(f"Plugin '{name}' no está ENABLED (estado: {entry.status.name})")
            return

        logger.info(f"Deshabilitando plugin '{name}'...")
        try:
            entry.instance.on_disable()  # type: ignore[union-attr]
            self._registry._update_entry(name, status=PluginStatus.DISABLED)
            logger.info(f"Plugin '{name}' deshabilitado")

        except Exception as exc:
            self._registry._update_entry(
                name, status=PluginStatus.ERROR, error_message=str(exc)
            )
            logger.error(f"Error al deshabilitar '{name}': {exc}")
            raise RuntimeError(f"Fallo al deshabilitar '{name}'") from exc

    # ------------------------------------------------------------------
    # Carga dinámica desde módulo
    # ------------------------------------------------------------------

    def load_from_module(
        self,
        module_path: str,
        class_name: str,
        plugin_name: str,
        **init_kwargs: Any,
    ) -> PluginInterface:
        """
        Carga un plugin dinámicamente desde una ruta de módulo Python.

        Args:
            module_path:  Ruta de módulo, p.ej. 'src.plugins.excel_import.plugin'
            class_name:   Nombre de la clase dentro del módulo.
            plugin_name:  Nombre único en el registry.
            init_kwargs:  Argumentos para initialize().

        Ejemplo:
            loader.load_from_module(
                "src.plugins.excel_import.plugin",
                "ExcelImportPlugin",
                "excel_import",
            )
        """
        logger.info(
            f"Carga dinámica: {module_path}.{class_name} → '{plugin_name}'"
        )
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            raise ImportError(
                f"No se pudo importar {module_path}.{class_name}: {exc}"
            ) from exc

        if not self._registry.exists(plugin_name):
            self._registry.register(plugin_name, plugin_class)

        return self.load(plugin_name, **init_kwargs)

    # ------------------------------------------------------------------
    # Helpers de estado
    # ------------------------------------------------------------------

    def is_enabled(self, name: str) -> bool:
        """Verifica si el plugin está en estado ENABLED."""
        entry = self._registry.get(name)
        return entry is not None and entry.status == PluginStatus.ENABLED

    def get_instance(self, name: str) -> Optional[PluginInterface]:
        """Retorna la instancia del plugin si existe, o None."""
        entry = self._registry.get(name)
        return entry.instance if entry else None


# ---------------------------------------------------------------------------
# Plugin Event Bus  (Observer entre plugins)
# ---------------------------------------------------------------------------

class PluginEventBus:
    """
    Canal de comunicación desacoplado entre plugins.
    Los plugins se comunican por eventos sin conocerse directamente.

    Diferencia con el EventBus principal del proyecto:
      - Este está scoped al sistema de plugins
      - Incluye log detallado de cada evento
      - Lleva historial para debugging

    Uso:
        bus = PluginEventBus()

        # Suscribirse
        bus.subscribe("producto.importado", mi_handler)

        # Publicar
        bus.publish("producto.importado", {"cantidad": 50, "tenant": "t1"})

        # Ver historial
        historial = bus.get_history("producto.importado")
    """

    def __init__(self, max_history: int = 100) -> None:
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._max_history = max_history
        self._lock = threading.RLock()
        logger.debug("PluginEventBus inicializado")

    def subscribe(self, event: str, handler: Callable) -> None:
        """
        Suscribe un handler a un evento.

        Args:
            event:   Nombre del evento (p.ej. 'producto.importado').
            handler: Callable que recibe el payload del evento.
        """
        with self._lock:
            if handler not in self._subscribers[event]:
                self._subscribers[event].append(handler)
                logger.debug(
                    f"PluginEventBus: '{handler.__name__}' suscrito a '{event}'"
                )

    def unsubscribe(self, event: str, handler: Callable) -> bool:
        """
        Desuscribe un handler de un evento.

        Returns:
            True si se eliminó, False si no estaba suscrito.
        """
        with self._lock:
            handlers = self._subscribers.get(event, [])
            if handler in handlers:
                handlers.remove(handler)
                logger.debug(
                    f"PluginEventBus: '{handler.__name__}' desuscrito de '{event}'"
                )
                return True
            return False

    def publish(self, event: str, data: Any = None) -> int:
        """
        Publica un evento notificando a todos los suscriptores.

        Args:
            event: Nombre del evento.
            data:  Payload del evento (cualquier tipo serializable).

        Returns:
            Número de handlers notificados.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event, []))

        # Guardar en historial
        record = {
            "event":     event,
            "data":      data,
            "timestamp": time.time(),
            "handlers":  len(handlers),
        }
        with self._lock:
            history = self._history[event]
            history.append(record)
            # Mantener límite de historial
            if len(history) > self._max_history:
                self._history[event] = history[-self._max_history:]

        if not handlers:
            logger.debug(f"PluginEventBus: '{event}' publicado, 0 suscriptores")
            return 0

        logger.debug(
            f"PluginEventBus: '{event}' → {len(handlers)} handler(s)"
        )

        errores = 0
        for handler in handlers:
            try:
                handler(data)
            except Exception as exc:
                errores += 1
                logger.error(
                    f"PluginEventBus: Error en handler '{handler.__name__}' "
                    f"para evento '{event}': {exc}"
                )

        if errores:
            logger.warning(
                f"PluginEventBus: {errores}/{len(handlers)} handlers fallaron "
                f"en evento '{event}'"
            )

        return len(handlers) - errores

    def get_history(
        self,
        event: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Retorna el historial de eventos.

        Args:
            event: Si se especifica, filtra por ese evento.
            limit: Máximo de registros a retornar.
        """
        with self._lock:
            if event:
                return list(self._history.get(event, []))[-limit:]
            # Todos los eventos, aplanados y ordenados por timestamp
            all_records = [
                rec
                for records in self._history.values()
                for rec in records
            ]
            all_records.sort(key=lambda r: r["timestamp"])
            return all_records[-limit:]

    def clear_history(self, event: Optional[str] = None) -> None:
        """Limpia el historial de un evento o de todos."""
        with self._lock:
            if event:
                self._history.pop(event, None)
            else:
                self._history.clear()
        logger.debug(
            f"PluginEventBus: historial limpiado "
            f"({'todos' if event is None else event})"
        )

    def subscriber_count(self, event: str) -> int:
        """Número de handlers suscritos a un evento."""
        with self._lock:
            return len(self._subscribers.get(event, []))


# ---------------------------------------------------------------------------
# Kernel Manager  (Fachada que une todo — DI-friendly)
# ---------------------------------------------------------------------------

class KernelManager:
    """
    Fachada principal del Micro-Kernel.
    Agrupa Registry, Loader y EventBus en un punto de entrada único.

    Diseño DI-friendly: puede recibir sus dependencias o crearlas.

    Uso:
        kernel = KernelManager()

        # Registrar y arrancar un plugin
        kernel.register_plugin("excel_import", ExcelImportPlugin)
        kernel.start_plugin("excel_import")

        # Comunicación entre plugins
        kernel.event_bus.publish("producto.importado", {"n": 50})

        # Acceder a instancia
        plugin = kernel.get_plugin("excel_import")
    """

    def __init__(
        self,
        registry:  Optional[PluginRegistry]  = None,
        loader:    Optional[PluginLoader]    = None,
        event_bus: Optional[PluginEventBus]  = None,
    ) -> None:
        self.registry  = registry  or PluginRegistry()
        self.event_bus = event_bus or PluginEventBus()
        self.loader    = loader    or PluginLoader(self.registry)
        logger.info("KernelManager inicializado")

    # ------------------------------------------------------------------
    # Shortcuts de alto nivel
    # ------------------------------------------------------------------

    def register_plugin(
        self,
        name: str,
        plugin_class: Type[PluginInterface],
    ) -> PluginInfo:
        """Registra un plugin en el catálogo."""
        return self.registry.register(name, plugin_class)

    def start_plugin(self, name: str, **init_kwargs: Any) -> PluginInterface:
        """Carga y habilita un plugin en un solo paso."""
        self.loader.load(name, **init_kwargs)
        return self.loader.enable(name)

    def stop_plugin(self, name: str) -> None:
        """Deshabilita y descarga un plugin."""
        self.loader.disable(name)
        self.loader.unload(name)

    def get_plugin(self, name: str) -> Optional[PluginInterface]:
        """Retorna la instancia activa de un plugin."""
        return self.loader.get_instance(name)

    def is_plugin_active(self, name: str) -> bool:
        """Verifica si un plugin está habilitado y operativo."""
        return self.loader.is_enabled(name)

    def active_plugins(self) -> List[str]:
        """Lista de plugins actualmente habilitados."""
        return self.registry.list_by_status(PluginStatus.ENABLED)

    def status_report(self) -> Dict[str, str]:
        """
        Reporte rápido de estado de todos los plugins.

        Returns:
            Dict {nombre: estado}
        """
        with self.registry._lock:
            return {
                name: entry.status.name
                for name, entry in self.registry._plugins.items()
            }