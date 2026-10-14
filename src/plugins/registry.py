"""
Plugin Registry - Registro centralizado de plugins (Singleton)
Gestiona el registro, descubrimiento y acceso a plugins
"""
from typing import Dict, List, Optional, Type
from threading import Lock

from src.core.logger import logger
from src.plugins.base import BasePlugin, PluginMetadata


class PluginRegistry:
    """
    Registro de plugins (Singleton).
    
    Mantiene un registro de todos los plugins disponibles
    y permite su descubrimiento y acceso.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Implementación del patrón Singleton thread-safe"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Inicializa el registry (solo una vez)"""
        if self._initialized:
            return
        
        self._plugins: Dict[str, Type[BasePlugin]] = {}
        self._plugin_instances: Dict[str, BasePlugin] = {}
        self._dependencies: Dict[str, List[str]] = {}
        self._initialized = True
        
        logger.info("Plugin Registry inicializado")
    
    # ==================== REGISTRATION ====================
    
    def register(
        self,
        plugin_class: Type[BasePlugin],
        metadata: Optional[PluginMetadata] = None
    ) -> None:
        """
        Registra una clase de plugin.
        
        Args:
            plugin_class: Clase del plugin a registrar
            metadata: Metadata del plugin (opcional)
            
        Raises:
            ValueError: Si el plugin ya está registrado
        """
        # Crear instancia temporal para obtener metadata
        if metadata is None:
            try:
                temp_instance = plugin_class.__new__(plugin_class)
                # Necesitamos inicializar _metadata manualmente
                if not hasattr(temp_instance, '_metadata'):
                    raise ValueError(
                        f"Plugin {plugin_class.__name__} debe definir metadata"
                    )
                metadata = temp_instance._metadata
            except Exception as e:
                raise ValueError(
                    f"No se pudo obtener metadata de {plugin_class.__name__}: {e}"
                )
        
        plugin_name = metadata.name
        
        if plugin_name in self._plugins:
            raise ValueError(
                f"Plugin '{plugin_name}' ya está registrado"
            )
        
        self._plugins[plugin_name] = plugin_class
        self._dependencies[plugin_name] = metadata.dependencies
        
        logger.info(
            f"Plugin registrado: {plugin_name} v{metadata.version}"
        )
    
    def unregister(self, plugin_name: str) -> None:
        """
        Desregistra un plugin.
        
        Args:
            plugin_name: Nombre del plugin a desregistrar
        """
        if plugin_name not in self._plugins:
            logger.warning(f"Plugin '{plugin_name}' no está registrado")
            return
        
        # Eliminar instancia si existe
        if plugin_name in self._plugin_instances:
            del self._plugin_instances[plugin_name]
        
        del self._plugins[plugin_name]
        del self._dependencies[plugin_name]
        
        logger.info(f"Plugin desregistrado: {plugin_name}")
    
    # ==================== INSTANCE MANAGEMENT ====================
    
    def register_instance(
        self,
        plugin_name: str,
        instance: BasePlugin
    ) -> None:
        """
        Registra una instancia de plugin.
        
        Args:
            plugin_name: Nombre del plugin
            instance: Instancia del plugin
        """
        self._plugin_instances[plugin_name] = instance
        logger.debug(f"Instancia registrada: {plugin_name}")
    
    def get_instance(self, plugin_name: str) -> Optional[BasePlugin]:
        """
        Obtiene una instancia de plugin.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            Instancia del plugin o None si no existe
        """
        return self._plugin_instances.get(plugin_name)
    
    def remove_instance(self, plugin_name: str) -> None:
        """
        Elimina una instancia de plugin.
        
        Args:
            plugin_name: Nombre del plugin
        """
        if plugin_name in self._plugin_instances:
            del self._plugin_instances[plugin_name]
            logger.debug(f"Instancia eliminada: {plugin_name}")
    
    # ==================== DISCOVERY ====================
    
    def get_plugin_class(
        self,
        plugin_name: str
    ) -> Optional[Type[BasePlugin]]:
        """
        Obtiene la clase de un plugin.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            Clase del plugin o None si no existe
        """
        return self._plugins.get(plugin_name)
    
    def list_plugins(self) -> List[str]:
        """
        Lista todos los plugins registrados.
        
        Returns:
            Lista de nombres de plugins
        """
        return list(self._plugins.keys())
    
    def list_instances(self) -> List[str]:
        """
        Lista todas las instancias activas.
        
        Returns:
            Lista de nombres de plugins con instancias
        """
        return list(self._plugin_instances.keys())
    
    def is_registered(self, plugin_name: str) -> bool:
        """
        Verifica si un plugin está registrado.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si está registrado
        """
        return plugin_name in self._plugins
    
    def has_instance(self, plugin_name: str) -> bool:
        """
        Verifica si existe una instancia del plugin.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si existe instancia
        """
        return plugin_name in self._plugin_instances
    
    # ==================== DEPENDENCIES ====================
    
    def get_dependencies(self, plugin_name: str) -> List[str]:
        """
        Obtiene las dependencias de un plugin.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            Lista de nombres de plugins dependientes
        """
        return self._dependencies.get(plugin_name, [])
    
    def check_dependencies(self, plugin_name: str) -> bool:
        """
        Verifica si las dependencias de un plugin están satisfechas.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si todas las dependencias están disponibles
        """
        dependencies = self.get_dependencies(plugin_name)
        
        for dep in dependencies:
            if not self.is_registered(dep):
                logger.warning(
                    f"Dependencia faltante para {plugin_name}: {dep}"
                )
                return False
        
        return True
    
    def get_load_order(self) -> List[str]:
        """
        Calcula el orden de carga basado en dependencias.
        
        Returns:
            Lista ordenada de nombres de plugins
            
        Raises:
            ValueError: Si hay dependencias circulares
        """
        order = []
        visited = set()
        temp_mark = set()
        
        def visit(plugin_name: str):
            if plugin_name in temp_mark:
                raise ValueError(
                    f"Dependencia circular detectada: {plugin_name}"
                )
            
            if plugin_name in visited:
                return
            
            temp_mark.add(plugin_name)
            
            for dep in self.get_dependencies(plugin_name):
                if self.is_registered(dep):
                    visit(dep)
            
            temp_mark.remove(plugin_name)
            visited.add(plugin_name)
            order.append(plugin_name)
        
        for plugin_name in self._plugins.keys():
            if plugin_name not in visited:
                visit(plugin_name)
        
        return order
    
    # ==================== UTILITY ====================
    
    def clear(self) -> None:
        """Limpia el registro (útil para testing)"""
        self._plugins.clear()
        self._plugin_instances.clear()
        self._dependencies.clear()
        logger.info("Plugin Registry limpiado")
    
    def get_stats(self) -> Dict:
        """
        Obtiene estadísticas del registry.
        
        Returns:
            Diccionario con estadísticas
        """
        return {
            "total_plugins": len(self._plugins),
            "active_instances": len(self._plugin_instances),
            "plugins": list(self._plugins.keys()),
            "instances": list(self._plugin_instances.keys())
        }
    
    def __repr__(self) -> str:
        return (
            f"PluginRegistry("
            f"plugins={len(self._plugins)}, "
            f"instances={len(self._plugin_instances)})"
        )


# ==================== DECORATORS ====================

def register_plugin(registry: Optional[PluginRegistry] = None):
    """
    Decorador para auto-registrar plugins.
    
    Usage:
        @register_plugin()
        class MyPlugin(BasePlugin):
            ...
    
    Args:
        registry: Registry donde registrar (usa el singleton si no se provee)
    """
    def decorator(plugin_class: Type[BasePlugin]):
        reg = registry or PluginRegistry()
        reg.register(plugin_class)
        return plugin_class
    return decorator