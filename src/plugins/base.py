"""
Plugin Base - Interface abstracta para todos los plugins
Implementa el patrón Template Method para lifecycle management
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from enum import Enum

from src.core.logger import logger
from src.core.event_bus import EventBus
from src.core.tenant_context import TenantContext


class PluginStatus(Enum):
    """Estados posibles de un plugin"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class PluginMetadata:
    """Metadata de un plugin"""
    
    def __init__(
        self,
        name: str,
        version: str,
        description: str,
        author: str = "Unknown",
        dependencies: Optional[List[str]] = None,
        tenant_specific: bool = True
    ):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.dependencies = dependencies or []
        self.tenant_specific = tenant_specific
        self.created_at = datetime.now(timezone.utc)
    
    def __repr__(self) -> str:
        return (
            f"PluginMetadata(name='{self.name}', "
            f"version='{self.version}', "
            f"tenant_specific={self.tenant_specific})"
        )


class BasePlugin(ABC):
    """
    Clase base abstracta para todos los plugins.
    
    Implementa el patrón Template Method para el ciclo de vida:
    1. initialize() -> on_initialize()
    2. start() -> on_start()
    3. stop() -> on_stop()
    
    Todos los plugins deben heredar de esta clase e implementar
    los métodos abstractos.
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        tenant_context: Optional[TenantContext] = None
    ):
        """
        Inicializa el plugin base.
        
        Args:
            event_bus: Bus de eventos para comunicación
            tenant_context: Contexto del tenant (si aplica)
        """
        self._event_bus = event_bus
        self._tenant_context = tenant_context
        self._status = PluginStatus.UNINITIALIZED
        self._config: Dict[str, Any] = {}
        self._error: Optional[str] = None
        
        # Metadata debe ser definida por cada plugin
        self._metadata: Optional[PluginMetadata] = None
    
    # ==================== PROPERTIES ====================
    
    @property
    def metadata(self) -> PluginMetadata:
        """Retorna metadata del plugin"""
        if self._metadata is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must define metadata"
            )
        return self._metadata
    
    @property
    def status(self) -> PluginStatus:
        """Estado actual del plugin"""
        return self._status
    
    @property
    def is_running(self) -> bool:
        """Verifica si el plugin está corriendo"""
        return self._status == PluginStatus.RUNNING
    
    @property
    def event_bus(self) -> EventBus:
        """Bus de eventos"""
        return self._event_bus
    
    @property
    def tenant_context(self) -> Optional[TenantContext]:
        """Contexto del tenant"""
        return self._tenant_context
    
    @property
    def config(self) -> Dict[str, Any]:
        """Configuración del plugin"""
        return self._config
    
    @property
    def error(self) -> Optional[str]:
        """Último error ocurrido"""
        return self._error
    
    # ==================== LIFECYCLE METHODS ====================
    
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Inicializa el plugin (Template Method).
        
        Args:
            config: Configuración específica del plugin
            
        Returns:
            True si la inicialización fue exitosa
        """
        if self._status != PluginStatus.UNINITIALIZED:
            logger.warning(
                f"Plugin {self.metadata.name} ya fue inicializado"
            )
            return False
        
        try:
            self._status = PluginStatus.INITIALIZING
            self._config = config or {}
            
            logger.info(
                f"Inicializando plugin: {self.metadata.name} v{self.metadata.version}"
            )
            
            # Llamar al hook del plugin específico
            self.on_initialize()
            
            self._status = PluginStatus.INITIALIZED
            self._emit_event("plugin.initialized", {
                "plugin": self.metadata.name,
                "version": self.metadata.version
            })
            
            logger.success(
                f"Plugin {self.metadata.name} inicializado correctamente"
            )
            return True
            
        except Exception as e:
            self._status = PluginStatus.ERROR
            self._error = str(e)
            logger.error(
                f"Error inicializando plugin {self.metadata.name}: {e}"
            )
            return False
    
    def start(self) -> bool:
        """
        Inicia el plugin (Template Method).
        
        Returns:
            True si el inicio fue exitoso
        """
        if self._status != PluginStatus.INITIALIZED:
            logger.warning(
                f"Plugin {self.metadata.name} debe ser inicializado primero"
            )
            return False
        
        try:
            self._status = PluginStatus.STARTING
            
            logger.info(f"Iniciando plugin: {self.metadata.name}")
            
            # Llamar al hook del plugin específico
            self.on_start()
            
            self._status = PluginStatus.RUNNING
            self._emit_event("plugin.started", {
                "plugin": self.metadata.name
            })
            
            logger.success(
                f"Plugin {self.metadata.name} iniciado correctamente"
            )
            return True
            
        except Exception as e:
            self._status = PluginStatus.ERROR
            self._error = str(e)
            logger.error(
                f"Error iniciando plugin {self.metadata.name}: {e}"
            )
            return False
    
    def stop(self) -> bool:
        """
        Detiene el plugin (Template Method).
        
        Returns:
            True si la detención fue exitosa
        """
        if self._status != PluginStatus.RUNNING:
            logger.warning(
                f"Plugin {self.metadata.name} no está corriendo"
            )
            return False
        
        try:
            self._status = PluginStatus.STOPPING
            
            logger.info(f"Deteniendo plugin: {self.metadata.name}")
            
            # Llamar al hook del plugin específico
            self.on_stop()
            
            self._status = PluginStatus.STOPPED
            self._emit_event("plugin.stopped", {
                "plugin": self.metadata.name
            })
            
            logger.success(
                f"Plugin {self.metadata.name} detenido correctamente"
            )
            return True
            
        except Exception as e:
            self._status = PluginStatus.ERROR
            self._error = str(e)
            logger.error(
                f"Error deteniendo plugin {self.metadata.name}: {e}"
            )
            return False
    
    # ==================== ABSTRACT METHODS (Hooks) ====================
    
    @abstractmethod
    def on_initialize(self) -> None:
        """
        Hook llamado durante la inicialización.
        Debe ser implementado por cada plugin específico.
        """
        pass
    
    @abstractmethod
    def on_start(self) -> None:
        """
        Hook llamado al iniciar el plugin.
        Debe ser implementado por cada plugin específico.
        """
        pass
    
    @abstractmethod
    def on_stop(self) -> None:
        """
        Hook llamado al detener el plugin.
        Debe ser implementado por cada plugin específico.
        """
        pass
    
    # ==================== HELPER METHODS ====================
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Emite un evento al bus.
        
        Args:
            event_type: Tipo de evento
            data: Datos del evento
        """
        # Agregar información del tenant si está disponible
        if self._tenant_context:
            data["tenant_id"] = self._tenant_context.tenant_id
        
        self._event_bus.publish(event_type, data)
    
    def _subscribe_to_event(
        self,
        event_type: str,
        callback: callable
    ) -> None:
        """
        Suscribe el plugin a un evento.
        
        Args:
            event_type: Tipo de evento
            callback: Función a llamar cuando ocurra el evento
        """
        self._event_bus.subscribe(event_type, callback)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Obtiene un valor de configuración.
        
        Args:
            key: Clave de configuración
            default: Valor por defecto si no existe
            
        Returns:
            Valor de configuración
        """
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """
        Establece un valor de configuración.
        
        Args:
            key: Clave de configuración
            value: Valor a establecer
        """
        self._config[key] = value
    
    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.metadata.name}', "
            f"status={self._status.value})"
        )


class PluginException(Exception):
    """Excepción base para errores de plugins"""
    pass


class PluginInitializationError(PluginException):
    """Error durante la inicialización de un plugin"""
    pass


class PluginStartError(PluginException):
    """Error al iniciar un plugin"""
    pass


class PluginStopError(PluginException):
    """Error al detener un plugin"""
    pass