"""
Plugin System - Sistema modular de plugins
"""

from src.plugins.base import (
    BasePlugin,
    PluginStatus,
    PluginMetadata,
    PluginException,
    PluginInitializationError,
    PluginStartError,
    PluginStopError
)

from src.plugins.registry import (
    PluginRegistry,
    register_plugin
)

from src.plugins.manager import PluginManager

from src.plugins.decorators import (
    require_running,
    log_execution,
    measure_time,
    retry_on_failure,
    emit_event_on_error,
    cache_result,
    validate_config,
    tenant_aware,
    async_event
)


__all__ = [
    # Base classes
    "BasePlugin",
    "PluginStatus",
    "PluginMetadata",
    
    # Exceptions
    "PluginException",
    "PluginInitializationError",
    "PluginStartError",
    "PluginStopError",
    
    # Registry
    "PluginRegistry",
    "register_plugin",
    
    # Manager
    "PluginManager",
    
    # Decorators
    "require_running",
    "log_execution",
    "measure_time",
    "retry_on_failure",
    "emit_event_on_error",
    "cache_result",
    "validate_config",
    "tenant_aware",
    "async_event",
]