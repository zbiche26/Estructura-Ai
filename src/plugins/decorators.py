"""
Plugin Decorators - Decoradores útiles para desarrollo de plugins
Simplifica tareas comunes y agrega funcionalidad cross-cutting
"""
import functools
import time
from typing import Callable, Any

from src.core.logger import logger


def require_running(func: Callable) -> Callable:
    """
    Decorador que verifica que el plugin esté corriendo.
    
    Usage:
        @require_running
        def process_data(self, data):
            ...
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.is_running:
            raise RuntimeError(
                f"Plugin {self.metadata.name} no está corriendo"
            )
        return func(self, *args, **kwargs)
    return wrapper


def log_execution(func: Callable) -> Callable:
    """
    Decorador que registra la ejecución de un método.
    
    Usage:
        @log_execution
        def important_method(self, data):
            ...
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        plugin_name = getattr(
            self, 'metadata', type(self).__name__
        )
        if hasattr(plugin_name, 'name'):
            plugin_name = plugin_name.name
        
        logger.debug(
            f"[{plugin_name}] Ejecutando {func.__name__}"
        )
        
        try:
            result = func(self, *args, **kwargs)
            logger.debug(
                f"[{plugin_name}] {func.__name__} completado"
            )
            return result
        except Exception as e:
            logger.error(
                f"[{plugin_name}] Error en {func.__name__}: {e}"
            )
            raise
    
    return wrapper


def measure_time(func: Callable) -> Callable:
    """
    Decorador que mide el tiempo de ejecución.
    
    Usage:
        @measure_time
        def slow_operation(self, data):
            ...
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        plugin_name = getattr(
            self, 'metadata', type(self).__name__
        )
        if hasattr(plugin_name, 'name'):
            plugin_name = plugin_name.name
        
        start_time = time.time()
        result = func(self, *args, **kwargs)
        elapsed = time.time() - start_time
        
        logger.debug(
            f"[{plugin_name}] {func.__name__} tomó {elapsed:.3f}s"
        )
        
        return result
    
    return wrapper


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """
    Decorador que reintenta una operación en caso de fallo.
    
    Args:
        max_retries: Número máximo de reintentos
        delay: Tiempo de espera entre reintentos (segundos)
    
    Usage:
        @retry_on_failure(max_retries=3, delay=2.0)
        def unreliable_operation(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            plugin_name = getattr(
                self, 'metadata', type(self).__name__
            )
            if hasattr(plugin_name, 'name'):
                plugin_name = plugin_name.name
            
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"[{plugin_name}] {func.__name__} falló "
                            f"(intento {attempt + 1}/{max_retries}). "
                            f"Reintentando en {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[{plugin_name}] {func.__name__} falló "
                            f"después de {max_retries} intentos"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def emit_event_on_error(event_type: str):
    """
    Decorador que emite un evento cuando ocurre un error.
    
    Args:
        event_type: Tipo de evento a emitir
    
    Usage:
        @emit_event_on_error("plugin.critical_error")
        def critical_operation(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                # Emitir evento de error
                if hasattr(self, '_emit_event'):
                    plugin_name = getattr(self, 'metadata', None)
                    if plugin_name and hasattr(plugin_name, 'name'):
                        plugin_name = plugin_name.name
                    else:
                        plugin_name = type(self).__name__
                    
                    self._emit_event(event_type, {
                        "plugin": plugin_name,
                        "method": func.__name__,
                        "error": str(e),
                        "error_type": type(e).__name__
                    })
                
                raise
        
        return wrapper
    return decorator


def cache_result(ttl: int = 60):
    """
    Decorador que cachea el resultado de una función.
    
    Args:
        ttl: Time to live en segundos
    
    Usage:
        @cache_result(ttl=300)
        def expensive_computation(self, param):
            ...
    """
    def decorator(func: Callable) -> Callable:
        cache = {}
        
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Crear key del cache
            cache_key = (args, tuple(sorted(kwargs.items())))
            
            # Verificar si está en cache y es válido
            if cache_key in cache:
                result, timestamp = cache[cache_key]
                if time.time() - timestamp < ttl:
                    logger.debug(
                        f"Cache hit para {func.__name__}"
                    )
                    return result
            
            # Ejecutar y cachear
            result = func(self, *args, **kwargs)
            cache[cache_key] = (result, time.time())
            
            logger.debug(
                f"Cache miss para {func.__name__}, resultado cacheado"
            )
            
            return result
        
        return wrapper
    return decorator


def validate_config(*required_keys: str):
    """
    Decorador que valida que existan ciertas keys de configuración.
    
    Args:
        *required_keys: Keys requeridas en la configuración
    
    Usage:
        @validate_config("api_key", "endpoint")
        def connect_to_api(self):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, 'config'):
                raise AttributeError(
                    f"{type(self).__name__} no tiene configuración"
                )
            
            missing_keys = [
                key for key in required_keys
                if key not in self.config
            ]
            
            if missing_keys:
                raise ValueError(
                    f"Faltan keys de configuración: {', '.join(missing_keys)}"
                )
            
            return func(self, *args, **kwargs)
        
        return wrapper
    return decorator


def tenant_aware(func: Callable) -> Callable:
    """
    Decorador que verifica que exista un tenant_context.
    
    Usage:
        @tenant_aware
        def tenant_specific_operation(self):
            ...
    """
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not hasattr(self, '_tenant_context'):
            raise AttributeError(
                f"{type(self).__name__} no tiene tenant_context"
            )
        
        if self._tenant_context is None:
            raise ValueError(
                "tenant_context es None, operación requiere tenant"
            )
        
        return func(self, *args, **kwargs)
    
    return wrapper


def async_event(event_type: str):
    """
    Decorador que emite un evento antes de ejecutar una función.
    
    Args:
        event_type: Tipo de evento a emitir
    
    Usage:
        @async_event("plugin.processing_started")
        def process_data(self, data):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # Emitir evento antes
            if hasattr(self, '_emit_event'):
                plugin_name = getattr(self, 'metadata', None)
                if plugin_name and hasattr(plugin_name, 'name'):
                    plugin_name = plugin_name.name
                else:
                    plugin_name = type(self).__name__
                
                self._emit_event(event_type, {
                    "plugin": plugin_name,
                    "method": func.__name__,
                    "args_count": len(args),
                    "kwargs_keys": list(kwargs.keys())
                })
            
            return func(self, *args, **kwargs)
        
        return wrapper
    return decorator