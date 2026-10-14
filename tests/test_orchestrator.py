"""
Tests para PluginOrchestrator
"""
import pytest
from typing import Dict, Any

from src.core.event_bus import EventBus
from src.plugins.orchestrator import (
    PluginOrchestrator,
    WorkflowStep,
    WorkflowStatus
)
from src.plugins.excel_import_plugin import ExcelImportPlugin
from src.plugins.inventory_plugin import InventoryPlugin


# ==================== FIXTURES ====================

@pytest.fixture
def event_bus():
    """Event bus limpio"""
    return EventBus()


@pytest.fixture
def mock_repository():
    """Mock de ProductRepository"""
    class MockRepository:
        def __init__(self):
            self.products = []
        
        def create(self, product_data: Dict[str, Any]):
            self.products.append(product_data)
            return product_data
        
        def get_all(self):
            return [
                {"id": "1", "name": "Laptop", "stock": 5, "min_stock": 10, "price": 999},
                {"id": "2", "name": "Mouse", "stock": 0, "min_stock": 20, "price": 25}
            ]
    
    return MockRepository()


@pytest.fixture
def orchestrator(event_bus):
    """Orchestrator configurado"""
    return PluginOrchestrator(event_bus)


# ==================== TESTS ====================

class TestOrchestratorBasics:
    """Tests bÃ¡sicos del orquestador"""
    
    def test_orchestrator_creation(self, event_bus):
        """Verifica creaciÃ³n del orquestador"""
        orch = PluginOrchestrator(event_bus)
        
        assert orch.event_bus == event_bus
        assert orch.plugin_manager is not None
        assert isinstance(orch._stats, dict)
    
    def test_orchestrator_initialization(self, orchestrator):
        """Verifica inicializaciÃ³n correcta"""
        stats = orchestrator.get_stats()
        
        assert stats["workflows_executed"] == 0
        assert stats["total_plugins"] == 0
        assert stats["active_plugins"] == 0


class TestPluginManagement:
    """Tests de gestiÃ³n de plugins"""
    
    def test_register_plugin(self, orchestrator, mock_repository):
        """Verifica registro de plugin"""
        success = orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        
        assert success
        assert orchestrator._stats["total_plugins"] == 1
    
    def test_register_multiple_plugins(self, orchestrator, mock_repository):
        """Verifica registro de mÃºltiples plugins"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        
        assert orchestrator._stats["total_plugins"] == 2
    
    def test_start_plugin(self, orchestrator, mock_repository):
        """Verifica inicio de plugin"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        
        success = orchestrator.start_plugin("excel_import")
        
        assert success
        assert orchestrator._stats["active_plugins"] == 1
    
    def test_stop_plugin(self, orchestrator, mock_repository):
        """Verifica detenciÃ³n de plugin"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        orchestrator.start_plugin("excel_import")
        
        success = orchestrator.stop_plugin("excel_import")
        
        assert success
        assert orchestrator._stats["active_plugins"] == 0
    
    def test_start_all_plugins(self, orchestrator, mock_repository):
        """Verifica inicio de todos los plugins"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        
        results = orchestrator.start_all_plugins()
        
        assert len(results) == 2
        assert all(results.values())
        assert orchestrator._stats["active_plugins"] == 2
    
    def test_stop_all_plugins(self, orchestrator, mock_repository):
        """Verifica detenciÃ³n de todos los plugins"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_all_plugins()
        
        results = orchestrator.stop_all_plugins()
        
        assert len(results) == 2
        assert all(results.values())
        assert orchestrator._stats["active_plugins"] == 0
    
    def test_get_plugin_status(self, orchestrator, mock_repository):
        """Verifica obtenciÃ³n de estado de plugins"""
        orchestrator.register_plugin(
            ExcelImportPlugin,
            {"repository": mock_repository}
        )
        orchestrator.start_plugin("excel_import")
        
        status = orchestrator.get_plugin_status()
        
        assert "excel_import" in status
        assert status["excel_import"]["name"] == "excel_import"
        assert status["excel_import"]["is_running"] is True


class TestWorkflowDefinition:
    """Tests de definiciÃ³n de workflows"""
    
    def test_define_workflow(self, orchestrator):
        """Verifica definiciÃ³n de workflow"""
        steps = [
            WorkflowStep(
                name="step1",
                plugin_name="test_plugin",
                method="test_method",
                params={}
            )
        ]
        
        orchestrator.define_workflow("test_workflow", steps)
        
        assert "test_workflow" in orchestrator._workflow_definitions
        assert len(orchestrator._workflow_definitions["test_workflow"]) == 1
    
    def test_define_multi_step_workflow(self, orchestrator):
        """Verifica workflow con mÃºltiples pasos"""
        steps = [
            WorkflowStep("step1", "plugin1", "method1", {}),
            WorkflowStep("step2", "plugin2", "method2", {}),
            WorkflowStep("step3", "plugin3", "method3", {})
        ]
        
        orchestrator.define_workflow("multi_step", steps)
        
        assert len(orchestrator._workflow_definitions["multi_step"]) == 3


class TestWorkflowExecution:
    """Tests de ejecuciÃ³n de workflows"""
    
    def test_execute_simple_workflow(self, orchestrator, mock_repository):
        """Verifica ejecuciÃ³n de workflow simple"""
        # Registrar e iniciar plugin
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        # Definir workflow
        steps = [
            WorkflowStep(
                name="check_inventory",
                plugin_name="inventory_plugin",
                method="check_inventory",
                params={}
            )
        ]
        orchestrator.define_workflow("simple_check", steps)
        
        # Ejecutar
        result = orchestrator.execute_workflow("simple_check")
        
        assert result.status == WorkflowStatus.COMPLETED
        assert result.steps_completed == 1
        assert result.steps_total == 1
        assert "check_inventory" in result.results
    
    def test_execute_undefined_workflow(self, orchestrator):
        """Verifica error con workflow no definido"""
        with pytest.raises(ValueError, match="no definido"):
            orchestrator.execute_workflow("undefined_workflow")
    
    def test_workflow_with_failing_step(self, orchestrator, mock_repository):
        """Verifica manejo de paso fallido"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        # Definir workflow con mÃ©todo invÃ¡lido
        steps = [
            WorkflowStep(
                name="invalid_step",
                plugin_name="inventory_plugin",
                method="non_existent_method",  # MÃ©todo que no existe
                params={}
            )
        ]
        orchestrator.define_workflow("failing_workflow", steps)
        
        # Ejecutar
        result = orchestrator.execute_workflow("failing_workflow")
        
        assert result.status == WorkflowStatus.FAILED
        assert len(result.errors) > 0
    
    def test_workflow_stats_update(self, orchestrator, mock_repository):
        """Verifica actualizaciÃ³n de estadÃ­sticas"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orchestrator.define_workflow("stats_test", steps)
        
        # Ejecutar
        orchestrator.execute_workflow("stats_test")
        
        stats = orchestrator.get_stats()
        
        assert stats["workflows_executed"] == 1
        assert stats["workflows_successful"] == 1
        assert stats["workflows_failed"] == 0


class TestWorkflowContext:
    """Tests de contexto de workflows"""
    
    def test_workflow_with_initial_data(self, orchestrator, mock_repository):
        """Verifica workflow con datos iniciales"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "analyze",
                "inventory_plugin",
                "analyze_trends",
                {"product_id": "$context.product_id", "days": 30}
            )
        ]
        orchestrator.define_workflow("context_test", steps)
        
        # Ejecutar con datos iniciales
        result = orchestrator.execute_workflow(
            "context_test",
            initial_data={"product_id": "prod_1"}
        )
        
        assert result.status == WorkflowStatus.COMPLETED
        assert "analyze" in result.results


class TestWorkflowControl:
    """Tests de control de workflows"""
    
    def test_get_workflow_result(self, orchestrator, mock_repository):
        """Verifica obtenciÃ³n de resultado"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orchestrator.define_workflow("result_test", steps)
        
        # Ejecutar
        result = orchestrator.execute_workflow("result_test")
        
        # Obtener resultado guardado
        saved_result = orchestrator.get_workflow_result(result.workflow_id)
        
        assert saved_result is not None
        assert saved_result.workflow_id == result.workflow_id


class TestHealthCheck:
    """Tests de health check"""
    
    def test_health_check_all(self, orchestrator, mock_repository):
        """Verifica health check de todos los plugins"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        health = orchestrator.health_check_all()
        
        assert "timestamp" in health
        assert "plugins" in health
        assert "overall_status" in health
        assert "inventory_plugin" in health["plugins"]
    
    def test_health_check_healthy_status(self, orchestrator, mock_repository):
        """Verifica estado healthy cuando todo estÃ¡ bien"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        health = orchestrator.health_check_all()
        
        assert health["overall_status"] == "healthy"


class TestEventEmission:
    """Tests de emisiÃ³n de eventos"""
    
    def test_emits_workflow_started_event(
        self,
        event_bus,
        mock_repository
    ):
        """Verifica evento de inicio de workflow"""
        events = []
        event_bus.subscribe("workflow.started", lambda e: events.append(e))
        
        orch = PluginOrchestrator(event_bus)
        orch.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orch.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orch.define_workflow("event_test", steps)
        
        orch.execute_workflow("event_test")
        
        assert len(events) == 1
    
    def test_emits_workflow_completed_event(
        self,
        event_bus,
        mock_repository
    ):
        """Verifica evento de workflow completado"""
        events = []
        event_bus.subscribe("workflow.completed", lambda e: events.append(e))
        
        orch = PluginOrchestrator(event_bus)
        orch.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orch.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orch.define_workflow("completion_test", steps)
        
        orch.execute_workflow("completion_test")
        
        assert len(events) == 1
    
    def test_emits_workflow_step_events(
        self,
        event_bus,
        mock_repository
    ):
        """Verifica eventos de pasos de workflow"""
        started_events = []
        completed_events = []
        
        event_bus.subscribe(
            "workflow.step_started",
            lambda e: started_events.append(e)
        )
        event_bus.subscribe(
            "workflow.step_completed",
            lambda e: completed_events.append(e)
        )
        
        orch = PluginOrchestrator(event_bus)
        orch.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orch.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orch.define_workflow("step_events_test", steps)
        
        orch.execute_workflow("step_events_test")
        
        assert len(started_events) == 1
        assert len(completed_events) == 1


class TestStatistics:
    """Tests de estadÃ­sticas"""
    
    def test_get_stats(self, orchestrator):
        """Verifica obtenciÃ³n de estadÃ­sticas"""
        stats = orchestrator.get_stats()
        
        assert "workflows_executed" in stats
        assert "workflows_successful" in stats
        assert "workflows_failed" in stats
        assert "total_plugins" in stats
        assert "active_plugins" in stats
        assert "workflows_active" in stats
        assert "workflows_total" in stats
    
    def test_stats_track_workflows(self, orchestrator, mock_repository):
        """Verifica tracking de workflows en stats"""
        orchestrator.register_plugin(
            InventoryPlugin,
            {"product_repository": mock_repository}
        )
        orchestrator.start_plugin("inventory_plugin")
        
        steps = [
            WorkflowStep(
                "check", "inventory_plugin", "check_inventory", {}
            )
        ]
        orchestrator.define_workflow("stats_workflow", steps)
        
        # Ejecutar mÃºltiples veces
        orchestrator.execute_workflow("stats_workflow")
        orchestrator.execute_workflow("stats_workflow")
        
        stats = orchestrator.get_stats()
        
        assert stats["workflows_executed"] == 2
        assert stats["workflows_total"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
