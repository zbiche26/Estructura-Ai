"""
Plugin Orchestrator - Orquestación y gestión de múltiples plugins

Este módulo permite:
- Gestionar múltiples plugins
- Ejecutar workflows automáticos
- Coordinar comunicación entre plugins
- Monitorear estado global
- Automatizar procesos complejos
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from src.plugins.base import BasePlugin
from src.plugins.manager import PluginManager
from src.core.event_bus import EventBus
from src.core.tenant_context import TenantContext
from src.core.logger import logger


class WorkflowStatus(Enum):
    """Estados de un workflow"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """Paso de un workflow"""
    name: str
    plugin_name: str
    method: str
    params: Dict[str, Any]
    on_success: Optional[str] = None
    on_failure: Optional[str] = None
    timeout: Optional[int] = None


@dataclass
class WorkflowResult:
    """Resultado de un workflow"""
    workflow_id: str
    status: WorkflowStatus
    steps_completed: int
    steps_total: int
    results: Dict[str, Any]
    errors: List[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]


class PluginOrchestrator:
    """Orquestador de plugins para gestión y workflows"""
    
    def __init__(
        self,
        event_bus: EventBus,
        tenant_context: Optional[TenantContext] = None
    ):
        self.event_bus = event_bus
        self.tenant_context = tenant_context
        self.plugin_manager = PluginManager(event_bus)
        
        self._workflows: Dict[str, WorkflowResult] = {}
        self._workflow_definitions: Dict[str, List[WorkflowStep]] = {}
        self._active_workflows: Dict[str, bool] = {}
        
        self._stats = {
            "workflows_executed": 0,
            "workflows_successful": 0,
            "workflows_failed": 0,
            "total_plugins": 0,
            "active_plugins": 0
        }
        
        logger.info("PluginOrchestrator inicializado")
    
    def register_plugin(
        self,
        plugin_class: type,
        config: Dict[str, Any]
    ) -> bool:
        """Registra e inicializa un plugin"""
        try:
            # Paso 1: Crear instancia temporal para obtener metadata
            temp_plugin = plugin_class(self.event_bus, self.tenant_context)
            plugin_name = temp_plugin.metadata.name
            
            # Paso 2: Registrar en el registry si no está registrado
            if not self.plugin_manager._registry.is_registered(plugin_name):
                self.plugin_manager._registry.register(
                    plugin_class,
                    temp_plugin.metadata
                )
            
            # Paso 3: Inicializar (el manager creará su propia instancia)
            success = self.plugin_manager.initialize_plugin(plugin_name, config)
            
            if success:
                self._stats["total_plugins"] += 1
                logger.success(f"Plugin {plugin_name} registrado")
            
            return success
        except Exception as e:
            logger.error(f"Error registrando plugin: {e}")
            return False
    
    def start_plugin(self, plugin_name: str) -> bool:
        """Inicia un plugin específico"""
        success = self.plugin_manager.start_plugin(plugin_name)
        if success:
            self._stats["active_plugins"] += 1
        return success
    
    def stop_plugin(self, plugin_name: str) -> bool:
        """Detiene un plugin específico"""
        success = self.plugin_manager.stop_plugin(plugin_name)
        if success:
            self._stats["active_plugins"] -= 1
        return success
    
    def start_all_plugins(self) -> Dict[str, bool]:
        """Inicia todos los plugins registrados"""
        results = {}
        for plugin_name in self.plugin_manager._active_plugins.keys():
            success = self.start_plugin(plugin_name)
            results[plugin_name] = success
        logger.info(f"Iniciados {sum(results.values())}/{len(results)} plugins")
        return results
    
    def stop_all_plugins(self) -> Dict[str, bool]:
        """Detiene todos los plugins activos"""
        results = {}
        # Crear lista de nombres para no modificar dict durante iteración
        plugin_names = list(self.plugin_manager._active_plugins.keys())
        for plugin_name in plugin_names:
            success = self.stop_plugin(plugin_name)
            results[plugin_name] = success
        logger.info(f"Detenidos {sum(results.values())}/{len(results)} plugins")
        return results
    
    def get_plugin_status(self) -> Dict[str, Any]:
        """Obtiene el estado de todos los plugins"""
        status = {}
        for plugin_name, plugin in self.plugin_manager._active_plugins.items():
            status[plugin_name] = {
                "name": plugin.metadata.name,
                "version": plugin.metadata.version,
                "status": plugin.status.value,
                "is_running": plugin.is_running,
                "description": plugin.metadata.description
            }
        return status
    
    def define_workflow(self, workflow_name: str, steps: List[WorkflowStep]) -> None:
        """Define un nuevo workflow"""
        self._workflow_definitions[workflow_name] = steps
        logger.info(f"Workflow '{workflow_name}' definido con {len(steps)} pasos")
    
    def execute_workflow(
        self,
        workflow_name: str,
        initial_data: Optional[Dict[str, Any]] = None
    ) -> WorkflowResult:
        """Ejecuta un workflow definido"""
        if workflow_name not in self._workflow_definitions:
            raise ValueError(f"Workflow '{workflow_name}' no definido")
        
        workflow_id = f"{workflow_name}_{datetime.now(timezone.utc).timestamp()}"
        
        result = WorkflowResult(
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            steps_completed=0,
            steps_total=len(self._workflow_definitions[workflow_name]),
            results={},
            errors=[],
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            duration_seconds=None
        )
        
        self._workflows[workflow_id] = result
        self._active_workflows[workflow_id] = True
        self._stats["workflows_executed"] += 1
        
        logger.info(f"Iniciando workflow '{workflow_name}' ({workflow_id})")
        self.event_bus.publish("workflow.started", {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name
        })
        
        try:
            context = initial_data or {}
            steps = self._workflow_definitions[workflow_name]
            
            for i, step in enumerate(steps):
                if not self._active_workflows.get(workflow_id, False):
                    result.status = WorkflowStatus.CANCELLED
                    break
                
                self.event_bus.publish("workflow.step_started", {
                    "workflow_id": workflow_id,
                    "step_name": step.name
                })
                
                try:
                    step_result = self._execute_step(step, context)
                    result.results[step.name] = step_result
                    result.steps_completed += 1
                    
                    if isinstance(step_result, dict):
                        context.update(step_result)
                    
                    self.event_bus.publish("workflow.step_completed", {
                        "workflow_id": workflow_id,
                        "step_name": step.name
                    })
                except Exception as e:
                    error_msg = f"Error en paso '{step.name}': {str(e)}"
                    result.errors.append(error_msg)
                    logger.error(error_msg)
                    raise
            
            result.status = WorkflowStatus.COMPLETED
            result.completed_at = datetime.now(timezone.utc)
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()
            
            self._stats["workflows_successful"] += 1
            logger.success(f"Workflow completado en {result.duration_seconds:.2f}s")
            
            self.event_bus.publish("workflow.completed", {
                "workflow_id": workflow_id,
                "duration": result.duration_seconds
            })
            
        except Exception as e:
            result.status = WorkflowStatus.FAILED
            result.completed_at = datetime.now(timezone.utc)
            result.duration_seconds = (
                result.completed_at - result.started_at
            ).total_seconds()
            result.errors.append(str(e))
            
            self._stats["workflows_failed"] += 1
            logger.error(f"Workflow falló: {e}")
            
            self.event_bus.publish("workflow.failed", {
                "workflow_id": workflow_id,
                "error": str(e)
            })
        finally:
            self._active_workflows[workflow_id] = False
        
        return result
    
    def _execute_step(self, step: WorkflowStep, context: Dict[str, Any]) -> Any:
        """Ejecuta un paso del workflow"""
        plugin = self.plugin_manager._active_plugins.get(step.plugin_name)
        
        if not plugin:
            raise ValueError(f"Plugin '{step.plugin_name}' no encontrado")
        
        if not plugin.is_running:
            raise RuntimeError(f"Plugin '{step.plugin_name}' no está corriendo")
        
        method = getattr(plugin, step.method, None)
        if not method:
            raise AttributeError(
                f"Método '{step.method}' no encontrado en '{step.plugin_name}'"
            )
        
        params = {}
        for key, value in step.params.items():
            if isinstance(value, str) and value.startswith("$context."):
                context_key = value.replace("$context.", "")
                params[key] = context.get(context_key)
            else:
                params[key] = value
        
        logger.debug(f"Ejecutando {step.plugin_name}.{step.method}")
        return method(**params)
    
    def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancela un workflow en ejecución"""
        if workflow_id in self._active_workflows:
            self._active_workflows[workflow_id] = False
            logger.warning(f"Workflow {workflow_id} cancelado")
            return True
        return False
    
    def get_workflow_result(self, workflow_id: str) -> Optional[WorkflowResult]:
        """Obtiene el resultado de un workflow"""
        return self._workflows.get(workflow_id)
    
    def health_check_all(self) -> Dict[str, Any]:
        """Health check de todos los plugins"""
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "plugins": {},
            "overall_status": "healthy"
        }
        
        # Obtener health de todos los plugins desde el manager
        manager_health = self.plugin_manager.health_check()
        
        for plugin_name, plugin_health in manager_health.items():
            health["plugins"][plugin_name] = {
                "healthy": plugin_health["is_running"] and plugin_health["error"] is None,
                **plugin_health
            }
            
            # Si algún plugin no está healthy, cambiar estado general
            if not health["plugins"][plugin_name]["healthy"]:
                health["overall_status"] = "unhealthy"
        
        return health
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del orquestador"""
        return {
            **self._stats,
            "workflows_active": len([
                w for w, active in self._active_workflows.items() if active
            ]),
            "workflows_total": len(self._workflows)
        }
    
    