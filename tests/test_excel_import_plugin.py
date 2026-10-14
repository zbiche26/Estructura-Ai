"""
Tests para ExcelImportPlugin
"""
import pytest
import pandas as pd
from pathlib import Path
from typing import Dict, Any

from src.core.event_bus import EventBus
from src.plugins.excel_import_plugin import ExcelImportPlugin


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
    
    return MockRepository()


@pytest.fixture
def plugin(event_bus, mock_repository):
    """Plugin configurado"""
    plugin = ExcelImportPlugin(event_bus)
    config = {
        "repository": mock_repository,
        "batch_size": 10,
        "validate_on_read": True
    }
    plugin.initialize(config)
    plugin.start()
    return plugin


@pytest.fixture
def sample_csv_file(tmp_path):
    """Crea un archivo CSV de prueba"""
    csv_content = """name,price,stock,description
Producto 1,100.50,10,Descripcion 1
Producto 2,200.00,20,Descripcion 2
Producto 3,150.75,15,Descripcion 3
"""
    file_path = tmp_path / "test_products.csv"
    file_path.write_text(csv_content, encoding='utf-8')  
    return str(file_path)


@pytest.fixture
def sample_excel_file(tmp_path):
    """Crea un archivo Excel de prueba"""
    data = {
        "name": ["Producto A", "Producto B", "Producto C"],
        "price": [100.0, 200.0, 150.0],
        "stock": [10, 20, 15],
        "description": ["Desc A", "Desc B", "Desc C"]
    }
    df = pd.DataFrame(data)
    
    file_path = tmp_path / "test_products.xlsx"
    df.to_excel(file_path, index=False)
    return str(file_path)


@pytest.fixture
def invalid_csv_file(tmp_path):
    """Crea un CSV con datos inválidos"""
    csv_content = """name,price,stock
Producto 1,100.50,10
,200.00,20
Producto 3,invalid_price,15
Producto 4,300.00,invalid_stock
"""
    file_path = tmp_path / "invalid_products.csv"
    file_path.write_text(csv_content)
    return str(file_path)


# ==================== TESTS ====================

class TestExcelImportPluginBasics:
    """Tests básicos del plugin"""
    
    def test_plugin_creation(self, event_bus):
        """Verifica creación del plugin"""
        plugin = ExcelImportPlugin(event_bus)
        
        assert plugin.metadata.name == "excel_import"
        assert plugin.metadata.version == "1.0.0"
        assert plugin.status.value == "uninitialized"
    
    def test_plugin_initialization(self, event_bus, mock_repository):
        """Verifica inicialización con configuración"""
        plugin = ExcelImportPlugin(event_bus)
        config = {"repository": mock_repository}
        
        success = plugin.initialize(config)
        
        assert success
        assert plugin.status.value == "initialized"
    
    def test_plugin_requires_repository(self, event_bus):
        """Verifica que falle sin repository"""
        plugin = ExcelImportPlugin(event_bus)
        
        success = plugin.initialize({})
        
        assert not success, "La inicialización debería fallar sin repository"
        assert plugin.status.value == "error"
    
    def test_plugin_lifecycle(self, event_bus, mock_repository):
        """Verifica ciclo de vida completo"""
        plugin = ExcelImportPlugin(event_bus)
        plugin.initialize({"repository": mock_repository})
        
        assert plugin.start()
        assert plugin.is_running
        
        assert plugin.stop()
        assert not plugin.is_running


class TestFileReading:
    """Tests de lectura de archivos"""
    
    def test_read_csv_file(self, plugin, sample_csv_file):
        """Verifica lectura de CSV"""
        df = plugin.preview_file(sample_csv_file)
        
        assert len(df) == 3
        assert "name" in df.columns
        assert "price" in df.columns
    
    def test_read_excel_file(self, plugin, sample_excel_file):
        """Verifica lectura de Excel"""
        df = plugin.preview_file(sample_excel_file)
        
        assert len(df) == 3
        assert "name" in df.columns
    
    def test_read_nonexistent_file(self, plugin):
        """Verifica error con archivo inexistente"""
        with pytest.raises(FileNotFoundError):
            plugin.preview_file("nonexistent.csv")
    
    def test_read_unsupported_format(self, plugin, tmp_path):
        """Verifica error con formato no soportado"""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test")
        
        with pytest.raises(ValueError, match="no soportado"):
            plugin.preview_file(str(file_path))
    
    def test_preview_limits_rows(self, plugin, sample_csv_file):
        """Verifica que preview limite filas"""
        df = plugin.preview_file(sample_csv_file, rows=2)
        
        assert len(df) <= 2


class TestDataValidation:
    """Tests de validación de datos"""
    
    def test_validate_valid_data(self, plugin, sample_csv_file):
        """Verifica validación de datos correctos"""
        stats = plugin.import_file(sample_csv_file)
        
        assert stats["total_rows"] == 3
        assert stats["valid_rows"] == 3
        assert stats["invalid_rows"] == 0
    
    def test_validate_invalid_data(self, plugin, invalid_csv_file):
        """Verifica detección de datos inválidos"""
        stats = plugin.import_file(invalid_csv_file)
        
        assert stats["total_rows"] == 4
        assert stats["invalid_rows"] > 0
        assert len(stats["errors"]) > 0
    
    def test_validation_catches_empty_name(self, plugin, tmp_path):
        """Verifica que detecte nombres vacíos"""
        csv_content = """name,price
,100.00
"""
        file_path = tmp_path / "empty_name.csv"
        file_path.write_text(csv_content)
        
        stats = plugin.import_file(str(file_path))
        
        assert stats["invalid_rows"] == 1
    
    def test_validation_catches_invalid_price(self, plugin, tmp_path):
        """Verifica que detecte precios inválidos"""
        csv_content = """name,price
Producto,invalid
"""
        file_path = tmp_path / "invalid_price.csv"
        file_path.write_text(csv_content)
        
        stats = plugin.import_file(str(file_path))
        
        assert stats["invalid_rows"] == 1


class TestColumnMapping:
    """Tests de mapeo de columnas"""
    
    def test_column_mapping(self, plugin, tmp_path):
        """Verifica mapeo de columnas"""
        csv_content = """Nombre,Precio,Stock
Producto 1,100.00,10
"""
        file_path = tmp_path / "custom_columns.csv"
        file_path.write_text(csv_content)
        
        mapping = {
            "Nombre": "name",
            "Precio": "price",
            "Stock": "stock"
        }
        
        stats = plugin.import_file(str(file_path), column_mapping=mapping)
        
        assert stats["valid_rows"] == 1
    
    def test_mapping_with_missing_columns(self, plugin, tmp_path):
        """Verifica manejo de columnas faltantes en mapeo"""
        csv_content = """name,price
Producto 1,100.00
"""
        file_path = tmp_path / "missing_col.csv"
        file_path.write_text(csv_content)
        
        mapping = {
            "name": "name",
            "price": "price",
            "nonexistent": "stock"
        }
        
        # No debería fallar, solo advertir
        stats = plugin.import_file(str(file_path), column_mapping=mapping)
        assert stats["total_rows"] == 1


class TestImportStatistics:
    """Tests de estadísticas de importación"""
    
    def test_get_import_stats(self, plugin, sample_csv_file):
        """Verifica obtención de estadísticas"""
        plugin.import_file(sample_csv_file)
        
        stats = plugin.get_import_stats()
        
        assert "total_rows" in stats
        assert "valid_rows" in stats
        assert "invalid_rows" in stats
        assert "saved_products" in stats
    
    def test_stats_reset_between_imports(self, plugin, sample_csv_file):
        """Verifica que stats se reinicien entre importaciones"""
        plugin.import_file(sample_csv_file)
        stats1 = plugin.get_import_stats()
        
        plugin.import_file(sample_csv_file)
        stats2 = plugin.get_import_stats()
        
        assert stats1["total_rows"] == stats2["total_rows"]


class TestEventEmission:
    """Tests de emisión de eventos"""
    
    def test_emits_started_event(self, event_bus, mock_repository, sample_csv_file):
        """Verifica evento de inicio"""
        events = []
        event_bus.subscribe("excel_import.started", lambda e: events.append(e))
        
        plugin = ExcelImportPlugin(event_bus)
        plugin.initialize({"repository": mock_repository})
        plugin.start()
        
        plugin.import_file(sample_csv_file)
        
        assert len(events) == 1
    
    def test_emits_completed_event(self, event_bus, mock_repository, sample_csv_file):
        """Verifica evento de completado"""
        events = []
        event_bus.subscribe("excel_import.completed", lambda e: events.append(e))
        
        plugin = ExcelImportPlugin(event_bus)
        plugin.initialize({"repository": mock_repository})
        plugin.start()
        
        plugin.import_file(sample_csv_file)
        
        assert len(events) == 1
    
    def test_emits_progress_events(self, event_bus, mock_repository, tmp_path):
        """Verifica eventos de progreso"""
        # Crear archivo con muchas filas para generar progreso
        data = {"name": [f"Producto {i}" for i in range(50)],
                "price": [100.0] * 50}
        df = pd.DataFrame(data)
        file_path = tmp_path / "large.csv"
        df.to_csv(file_path, index=False)
        
        events = []
        event_bus.subscribe("excel_import.progress", lambda e: events.append(e))
        
        plugin = ExcelImportPlugin(event_bus)
        plugin.initialize({"repository": mock_repository, "batch_size": 10})
        plugin.start()
        
        plugin.import_file(str(file_path))
        
        assert len(events) >= 1


class TestErrorHandling:
    """Tests de manejo de errores"""
    
    def test_handles_file_not_found(self, plugin):
        """Verifica manejo de archivo no encontrado"""
        with pytest.raises(FileNotFoundError):
            plugin.import_file("nonexistent.csv")
    
    def test_requires_running_decorator(self, event_bus, mock_repository, sample_csv_file):
        """Verifica que requiere estar running"""
        plugin = ExcelImportPlugin(event_bus)
        plugin.initialize({"repository": mock_repository})
        # No llamamos start()
        
        with pytest.raises(RuntimeError, match="no está corriendo"):
            plugin.import_file(sample_csv_file)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])