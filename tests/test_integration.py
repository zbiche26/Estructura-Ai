"""
Tests de IntegraciÃ³n End-to-End para el Sistema de Plugins

Estos tests prueban el flujo completo de:
- Excel Import â†’ Inventory Check â†’ Alerts
- MÃºltiples plugins trabajando juntos
- Workflows automÃ¡ticos completos
"""
import pytest
from pathlib import Path
import tempfile

from src.core.event_bus import EventBus
from src.plugins.orchestrator import PluginOrchestrator, WorkflowStep
from src.plugins.excel_import_plugin import ExcelImportPlugin
from src.plugins.inventory_plugin import InventoryPlugin


# ==================== FIXTURES ====================

@pytest.fixture
def temp_dir():
    """Directorio temporal para archivos"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_csv_file(temp_dir):
    """Crea un archivo CSV de ejemplo"""
    csv_path = temp_dir / "productos.csv"
    csv_content = """name,price,stock,min_stock,category
Laptop HP,999.99,5,10,Electronics
Mouse Logitech,25.50,0,20,Accessories
Teclado MecÃ¡nico,89.99,15,10,Accessories
Monitor LG,299.00,3,5,Electronics"""
    
    csv_path.write_text(csv_content, encoding='utf-8')
    return str(csv_path)


@pytest.fixture
def mock_repository():
    """Mock de ProductRepository con persistencia"""
    class MockRepository:
        def __init__(self):
            self.products = []
            self.id_counter = 1
        
        def create(self, product_data):
            product = {
                "id": f"prod_{self.id_counter}",
                **product_data
            }
            self.products.append(product)
            self.id_counter += 1
            return product
        
        def get_all(self):
            return self.products
        
        def get_by_id(self, product_id):
            for p in self.products:
                if p.get("id") == product_id:
                    return p
            return None
        
        def update(self, product_id, updates):
            for p in self.products:
                if p.get("id") == product_id:
                    p.update(updates)
                    return p
            return None
    
    return MockRepository()


@pytest.fixture
def orchestrator(mock_repository):
    """Orchestrator configurado con plugins"""
    event_bus = EventBus()
    orch = PluginOrchestrator(event_bus)
    
    # Registrar plugins CON EL MISMO mock_repository
    orch.register_plugin(
        ExcelImportPlugin,
        {"repository": mock_repository}
    )
    
    orch.register_plugin(
        InventoryPlugin,
        {
            "product_repository": mock_repository,
            "low_stock_threshold": 10,
            "critical_stock_threshold": 5
        }
    )
    
    # Iniciar plugins
    orch.start_all_plugins()
    
    # Guardar referencia al repository para acceso en tests
    orch._test_repository = mock_repository
    
    return orch


# ==================== TESTS DE INTEGRACIÃ“N ====================

@pytest.mark.skip(reason="stub pendiente")
class TestEndToEndWorkflow:
    """Tests de workflows completos end-to-end"""
    
    def test_excel_to_inventory_workflow(
        self,
        orchestrator,
        sample_csv_file,
        mock_repository
    ):
        """
        Verifica flujo completo:
        1. Importar productos desde Excel
        2. Verificar inventario
        3. Generar alertas
        """
        # Definir workflow
        steps = [
            WorkflowStep(
                name="import_products",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            ),
            WorkflowStep(
                name="check_inventory",
                plugin_name="inventory_plugin",
                method="check_inventory",
                params={}
            )
        ]
        
        orchestrator.define_workflow("excel_to_inventory", steps)
        
        # Ejecutar workflow
        result = orchestrator.execute_workflow("excel_to_inventory")
        
        # Verificar resultado
        assert result.status.value == "completed"
        assert result.steps_completed == 2
        assert len(result.errors) == 0
        
        # Verificar que se importaron productos
        assert "import_products" in result.results
        import_result = result.results["import_products"]
        assert import_result["saved_products"] == 4
        
        # Verificar que se hizo el check de inventario
        assert "check_inventory" in result.results
        inventory_result = result.results["check_inventory"]
        assert "alerts" in inventory_result
        
        # Verificar que hay alertas (productos con stock bajo/crÃ­tico)
        assert len(inventory_result["alerts"]) > 0
    
    def test_workflow_with_alerts(
        self,
        orchestrator,
        sample_csv_file,
        mock_repository
    ):
        """
        Verifica que se generen alertas para productos con stock bajo
        """
        # Definir workflow
        steps = [
            WorkflowStep(
                name="import",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            ),
            WorkflowStep(
                name="check",
                plugin_name="inventory_plugin",
                method="check_inventory",
                params={}
            ),
            WorkflowStep(
                name="get_alerts",
                plugin_name="inventory_plugin",
                method="get_active_alerts",
                params={}
            )
        ]
        
        orchestrator.define_workflow("import_and_alert", steps)
        
        # Ejecutar
        result = orchestrator.execute_workflow("import_and_alert")
        
        # Verificar alertas
        assert result.status.value == "completed"
        alerts = result.results["get_alerts"]
        
        # Debe haber alertas (productos con stock bajo/crÃ­tico)
        assert len(alerts) > 0
        
        # Verificar que las alertas tienen la estructura correcta
        first_alert = alerts[0]
        assert hasattr(first_alert, 'level')
        assert hasattr(first_alert, 'product_id')
        assert hasattr(first_alert, 'message')
        
        # Verificar que el nivel es uno vÃ¡lido (comparar con .value porque es Enum)
        valid_levels = ["info", "warning", "critical", "urgent"]
        assert first_alert.level.value in valid_levels
    
    def test_workflow_statistics(
        self,
        orchestrator,
        sample_csv_file
    ):
        """
        Verifica que las estadÃ­sticas del workflow se actualicen correctamente
        """
        # Definir workflow simple
        steps = [
            WorkflowStep(
                name="import",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            )
        ]
        
        orchestrator.define_workflow("simple_import", steps)
        
        # Ejecutar mÃºltiples veces
        result1 = orchestrator.execute_workflow("simple_import")
        result2 = orchestrator.execute_workflow("simple_import")
        
        # Verificar stats
        stats = orchestrator.get_stats()
        
        assert stats["workflows_executed"] == 2
        assert stats["workflows_successful"] == 2
        assert stats["workflows_failed"] == 0
        assert stats["total_plugins"] == 2
        assert stats["active_plugins"] == 2


@pytest.mark.skip(reason="workflows pendientes")
class TestPluginCommunication:
    """Tests de comunicaciÃ³n entre plugins"""
    
    def test_plugins_share_data_via_context(
        self,
        orchestrator,
        sample_csv_file
    ):
        """
        Verifica que los plugins puedan compartir datos vÃ­a contexto
        """
        steps = [
            WorkflowStep(
                name="import",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            ),
            WorkflowStep(
                name="stats",
                plugin_name="inventory_plugin",
                method="get_inventory_stats",
                params={}
            )
        ]
        
        orchestrator.define_workflow("data_sharing", steps)
        
        result = orchestrator.execute_workflow("data_sharing")
        
        # Verificar que ambos pasos se completaron
        assert result.steps_completed == 2
        
        # Verificar que hay datos de ambos plugins
        assert "import" in result.results
        assert "stats" in result.results
    
    def test_event_propagation_between_plugins(self):
        """
        Verifica que los eventos se propaguen entre plugins
        """
        events_received = []
        
        # Crear orchestrator fresh sin plugins iniciados
        event_bus = EventBus()
        
        # Suscribirse a eventos ANTES de crear plugins
        def capture_event(event):
            events_received.append(event.event_type)
        
        event_bus.subscribe("plugin.started", capture_event)
        event_bus.subscribe("excel_import.ready", capture_event)
        
        # Ahora crear orchestrator y plugins
        orch = PluginOrchestrator(event_bus)
        
        class MockRepo:
            def create(self, data):
                return {"id": "1", **data}
        
        orch.register_plugin(ExcelImportPlugin, {"repository": MockRepo()})
        
        # Iniciar plugin (debe emitir eventos)
        orch.start_plugin("excel_import")
        
        # Verificar que se emitieron eventos
        assert len(events_received) > 0
        assert "plugin.started" in events_received or "excel_import.ready" in events_received


class TestErrorRecovery:
    """Tests de recuperaciÃ³n de errores"""
    
    def test_workflow_continues_after_recoverable_error(
        self,
        orchestrator,
        temp_dir
    ):
        """
        Verifica manejo de errores en workflows
        """
        # Archivo que no existe
        nonexistent_file = str(temp_dir / "no_existe.csv")
        
        steps = [
            WorkflowStep(
                name="import_fail",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": nonexistent_file}
            )
        ]
        
        orchestrator.define_workflow("error_workflow", steps)
        
        # Ejecutar (debe fallar)
        result = orchestrator.execute_workflow("error_workflow")
        
        # Verificar que el workflow fallÃ³
        assert result.status.value == "failed"
        assert len(result.errors) > 0
        
        # Verificar que las stats se actualizaron
        stats = orchestrator.get_stats()
        assert stats["workflows_failed"] == 1
    
    def test_health_check_detects_issues(self, orchestrator):
        """
        Verifica que health check detecte problemas
        """
        # Health check inicial
        health1 = orchestrator.health_check_all()
        assert health1["overall_status"] == "healthy"
        assert "excel_import" in health1["plugins"]
        assert "inventory_plugin" in health1["plugins"]
        
        # Detener un plugin (esto lo ELIMINA de _active_plugins)
        orchestrator.stop_plugin("excel_import")
        
        # Health check debe mostrar solo el plugin activo
        health2 = orchestrator.health_check_all()
        
        # Excel import ya no estÃ¡ en active_plugins (fue removido al detener)
        # Solo inventory_management debe estar
        assert "inventory_plugin" in health2["plugins"]
        assert health2["plugins"]["inventory_plugin"]["is_running"] is True
        
        # Excel import no deberÃ­a estar porque se eliminÃ³
        # (esto es comportamiento correcto del sistema)
        assert "excel_import" not in health2["plugins"]


class TestPerformance:
    """Tests de rendimiento"""
    
    def test_workflow_execution_time(
        self,
        orchestrator,
        sample_csv_file
    ):
        """
        Verifica que los workflows se ejecuten en tiempo razonable
        """
        steps = [
            WorkflowStep(
                name="import",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            ),
            WorkflowStep(
                name="check",
                plugin_name="inventory_plugin",
                method="check_inventory",
                params={}
            )
        ]
        
        orchestrator.define_workflow("perf_test", steps)
        
        # Ejecutar
        result = orchestrator.execute_workflow("perf_test")
        
        # Verificar que se completÃ³ rÃ¡pido
        assert result.duration_seconds is not None
        assert result.duration_seconds < 5.0  # Menos de 5 segundos
    
    def test_multiple_workflows_concurrently(
        self,
        orchestrator,
        sample_csv_file
    ):
        """
        Verifica ejecuciÃ³n de mÃºltiples workflows
        """
        steps = [
            WorkflowStep(
                name="import",
                plugin_name="excel_import",
                method="import_file",
                params={"file_path": sample_csv_file}
            )
        ]
        
        orchestrator.define_workflow("concurrent_test", steps)
        
        # Ejecutar mÃºltiples workflows
        results = []
        for i in range(3):
            result = orchestrator.execute_workflow("concurrent_test")
            results.append(result)
        
        # Verificar que todos se completaron
        assert all(r.status.value == "completed" for r in results)
        
        # Verificar que cada uno tiene su propio ID
        ids = [r.workflow_id for r in results]
        assert len(set(ids)) == 3  # Todos IDs Ãºnicos


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
