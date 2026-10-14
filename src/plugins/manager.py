"""
Plugin Manager - Gestiona el ciclo de vida de todos los plugins
Orquesta la inicialización, inicio y detención de plugins
"""
from typing import Dict, List, Optional, Any
from threading import Lock

from src.core.logger import logger
from src.core.event_bus import EventBus
from src.core.tenant_context import TenantContext
from src.plugins.base import BasePlugin, PluginStatus
from src.plugins.registry import PluginRegistry


class PluginManager:
    """
    Gestor de plugins.
    
    Responsable de:
    - Inicializar plugins en el orden correcto
    - Gestionar el ciclo de vida de plugins
    - Coordinar comunicación entre plugins
    - Manejar errores de plugins
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        registry: Optional[PluginRegistry] = None,
        tenant_context: Optional[TenantContext] = None
    ):
        """
        Inicializa el gestor de plugins.
        
        Args:
            event_bus: Bus de eventos global
            registry: Registry de plugins (usa singleton si no se provee)
            tenant_context: Contexto del tenant (si aplica)
        """
        self._event_bus = event_bus
        self._registry = registry or PluginRegistry()
        self._tenant_context = tenant_context
        self._lock = Lock()
        
        # Instancias activas (plugin_name -> instancia)
        self._active_plugins: Dict[str, BasePlugin] = {}
        
        logger.info("Plugin Manager inicializado")
    
    # ==================== LIFECYCLE ====================
    
    def initialize_plugin(
        self,
        plugin_name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Inicializa un plugin específico.
        
        Args:
            plugin_name: Nombre del plugin
            config: Configuración del plugin
            
        Returns:
            True si la inicialización fue exitosa
        """
        with self._lock:
            # Verificar si ya está inicializado
            if plugin_name in self._active_plugins:
                logger.warning(
                    f"Plugin {plugin_name} ya está inicializado"
                )
                return False
            
            # Verificar si el plugin está registrado
            if not self._registry.is_registered(plugin_name):
                logger.error(
                    f"Plugin {plugin_name} no está registrado"
                )
                return False
            
            # Verificar dependencias
            if not self._registry.check_dependencies(plugin_name):
                logger.error(
                    f"Dependencias no satisfechas para {plugin_name}"
                )
                return False
            
            try:
                # Crear instancia
                plugin_class = self._registry.get_plugin_class(plugin_name)
                instance = plugin_class(
                    event_bus=self._event_bus,
                    tenant_context=self._tenant_context
                )
                
                # Inicializar
                if not instance.initialize(config):
                    logger.error(
                        f"Falló la inicialización de {plugin_name}"
                    )
                    return False
                
                # Guardar instancia
                self._active_plugins[plugin_name] = instance
                self._registry.register_instance(plugin_name, instance)
                
                logger.success(
                    f"Plugin {plugin_name} inicializado correctamente"
                )
                return True
                
            except Exception as e:
                logger.error(
                    f"Error inicializando plugin {plugin_name}: {e}"
                )
                return False
    
    def start_plugin(self, plugin_name: str) -> bool:
        """
        Inicia un plugin específico.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si el inicio fue exitoso
        """
        with self._lock:
            if plugin_name not in self._active_plugins:
                logger.error(
                    f"Plugin {plugin_name} no está inicializado"
                )
                return False
            
            instance = self._active_plugins[plugin_name]
            return instance.start()
    
    def stop_plugin(self, plugin_name: str) -> bool:
        """
        Detiene un plugin específico.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si la detención fue exitosa
        """
        with self._lock:
            if plugin_name not in self._active_plugins:
                logger.warning(
                    f"Plugin {plugin_name} no está activo"
                )
                return False
            
            instance = self._active_plugins[plugin_name]
            success = instance.stop()
            
            if success:
                # Remover de activos
                del self._active_plugins[plugin_name]
                self._registry.remove_instance(plugin_name)
            
            return success
    
    # ==================== BATCH OPERATIONS ====================
    
    def initialize_all(
        self,
        configs: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> Dict[str, bool]:
        """
        Inicializa todos los plugins registrados.
        
        Args:
            configs: Diccionario de configuraciones por plugin
            
        Returns:
            Diccionario con resultados por plugin
        """
        configs = configs or {}
        results = {}
        
        try:
            # Obtener orden de carga
            load_order = self._registry.get_load_order()
            
            logger.info(
                f"Inicializando {len(load_order)} plugins en orden: "
                f"{', '.join(load_order)}"
            )
            
            for plugin_name in load_order:
                config = configs.get(plugin_name, {})
                success = self.initialize_plugin(plugin_name, config)
                results[plugin_name] = success
                
                if not success:
                    logger.error(
                        f"Falló inicialización de {plugin_name}, "
                        "deteniendo proceso"
                    )
                    break
            
            return results
            
        except Exception as e:
            logger.error(f"Error en inicialización batch: {e}")
            return results
    
    def start_all(self) -> Dict[str, bool]:
        """
        Inicia todos los plugins inicializados.
        
        Returns:
            Diccionario con resultados por plugin
        """
        results = {}
        
        for plugin_name in list(self._active_plugins.keys()):
            results[plugin_name] = self.start_plugin(plugin_name)
        
        successful = sum(1 for v in results.values() if v)
        logger.info(
            f"Iniciados {successful}/{len(results)} plugins"
        )
        
        return results
    
    def stop_all(self) -> Dict[str, bool]:
        """
        Detiene todos los plugins activos.
        
        Returns:
            Diccionario con resultados por plugin
        """
        results = {}
        
        # Detener en orden inverso
        for plugin_name in reversed(list(self._active_plugins.keys())):
            results[plugin_name] = self.stop_plugin(plugin_name)
        
        successful = sum(1 for v in results.values() if v)
        logger.info(
            f"Detenidos {successful}/{len(results)} plugins"
        )
        
        return results
    
    # ==================== QUERY ====================
    
    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """
        Obtiene una instancia de plugin activa.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            Instancia del plugin o None
        """
        return self._active_plugins.get(plugin_name)
    
    def get_plugin_status(self, plugin_name: str) -> Optional[PluginStatus]:
        """
        Obtiene el estado de un plugin.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            Estado del plugin o None si no existe
        """
        instance = self._active_plugins.get(plugin_name)
        return instance.status if instance else None
    
    def list_active_plugins(self) -> List[str]:
        """
        Lista todos los plugins activos.
        
        Returns:
            Lista de nombres de plugins
        """
        return list(self._active_plugins.keys())
    
    def list_running_plugins(self) -> List[str]:
        """
        Lista plugins que están corriendo.
        
        Returns:
            Lista de nombres de plugins en estado RUNNING
        """
        return [
            name for name, instance in self._active_plugins.items()
            if instance.status == PluginStatus.RUNNING
        ]
    
    def is_plugin_running(self, plugin_name: str) -> bool:
        """
        Verifica si un plugin está corriendo.
        
        Args:
            plugin_name: Nombre del plugin
            
        Returns:
            True si está corriendo
        """
        instance = self._active_plugins.get(plugin_name)
        return instance.is_running if instance else False
    
    # ==================== HEALTH CHECK ====================
    
    def health_check(self) -> Dict[str, Any]:
        """
        Realiza un chequeo de salud de todos los plugins.
        
        Returns:
            Diccionario con estado de cada plugin
        """
        health = {}
        
        for plugin_name, instance in self._active_plugins.items():
            health[plugin_name] = {
                "status": instance.status.value,
                "is_running": instance.is_running,
                "error": instance.error,
                "version": instance.metadata.version
            }
        
        return health
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas del gestor.
        
        Returns:
            Diccionario con estadísticas
        """
        total = len(self._registry.list_plugins())
        active = len(self._active_plugins)
        running = len(self.list_running_plugins())
        
        return {
            "total_registered": total,
            "active": active,
            "running": running,
            "inactive": total - active,
            "health": self.health_check()
        }
    
    # ==================== UTILITY ====================
    
    def reload_plugin(
        self,
        plugin_name: str,
        config: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Recarga un plugin (stop -> initialize -> start).
        
        Args:
            plugin_name: Nombre del plugin
            config: Nueva configuración
            
        Returns:
            True si la recarga fue exitosa
        """
        logger.info(f"Recargando plugin: {plugin_name}")
        
        # Detener si está activo
        if plugin_name in self._active_plugins:
            if not self.stop_plugin(plugin_name):
                logger.error(f"No se pudo detener {plugin_name}")
                return False
        
        # Reinicializar
        if not self.initialize_plugin(plugin_name, config):
            logger.error(f"No se pudo reinicializar {plugin_name}")
            return False
        
        # Reiniciar
        if not self.start_plugin(plugin_name):
            logger.error(f"No se pudo reiniciar {plugin_name}")
            return False
        
        logger.success(f"Plugin {plugin_name} recargado exitosamente")
        return True
    
    def __repr__(self) -> str:
        return (
            f"PluginManager("
            f"active={len(self._active_plugins)}, "
            f"running={len(self.list_running_plugins())})"
        )