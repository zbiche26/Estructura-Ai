"""
Tests para Factories
====================

Tests automatizados para el Factory Pattern.

Ejecutar: python -m pytest tests/test_factories.py -v
"""

import pytest
import pandas as pd
import tempfile
import os
from pathlib import Path
from src.core.factories import (
    EmbeddingFactory,
    ExcelParserFactory,
    LLMFactory,
    IEmbeddingGenerator,
    IExcelParser,
    ILLMClient
)


# ============================================
# TESTS DE EMBEDDING FACTORY
# ============================================

class TestEmbeddingFactory:
    """Tests para EmbeddingFactory"""
    
    def test_create_local_generator(self):
        """Test: Crear generador local"""
        generator = EmbeddingFactory.create('local')
        
        assert generator is not None
        assert isinstance(generator, IEmbeddingGenerator)
    
    def test_local_generator_generate(self):
        """Test: Generar embedding con generador local"""
        generator = EmbeddingFactory.create('local')
        
        text = "Laptop HP 15 pulgadas"
        embedding = generator.generate(text)
        
        # Verificar que sea una lista de números
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)
    
    def test_local_generator_dimension(self):
        """Test: Verificar dimensión del embedding local"""
        generator = EmbeddingFactory.create('local')
        dimension = generator.get_dimension()
        
        # all-MiniLM-L6-v2 tiene 384 dimensiones
        assert dimension == 384
    
    def test_local_generator_consistency(self):
        """Test: Mismo texto genera embeddings similares"""
        generator = EmbeddingFactory.create('local')
        
        text = "Producto de prueba"
        embedding1 = generator.generate(text)
        embedding2 = generator.generate(text)
        
        # Deberían ser exactamente iguales
        assert embedding1 == embedding2
    
    def test_different_texts_different_embeddings(self):
        """Test: Textos diferentes generan embeddings diferentes"""
        generator = EmbeddingFactory.create('local')
        
        embedding1 = generator.generate("laptop")
        embedding2 = generator.generate("mouse")
        
        # Deberían ser diferentes
        assert embedding1 != embedding2
    
    def test_provider_no_soportado(self):
        """Test: Provider no existente lanza error"""
        with pytest.raises(ValueError, match="no soportado"):
            EmbeddingFactory.create('provider_inexistente')
    
    def test_get_available_providers(self):
        """Test: Obtener lista de providers disponibles"""
        providers = EmbeddingFactory.get_available_providers()
        
        assert 'local' in providers
        assert 'openai' in providers
        assert len(providers) >= 2


# ============================================
# TESTS DE EXCEL PARSER FACTORY
# ============================================

class TestExcelParserFactory:
    """Tests para ExcelParserFactory"""
    
    def setup_method(self):
        """Crear DataFrame de prueba"""
        self.test_data = pd.DataFrame({
            'codigo': ['PROD-001', 'PROD-002', 'PROD-003'],
            'nombre': ['Laptop HP', 'Mouse Logitech', 'Teclado'],
            'precio': [850.00, 25.50, 45.00],
            'stock': [10, 50, 30]
        })
    
    def test_create_parser_for_csv(self):
        """Test: Crear parser para archivo CSV"""
        # Crear archivo temporal CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', 
                                        delete=False, newline='') as f:
            self.test_data.to_csv(f.name, index=False)
            temp_file = f.name
        
        try:
            # Crear parser
            parser = ExcelParserFactory.create_for_file(temp_file)
            assert parser is not None
            assert isinstance(parser, IExcelParser)
            
            # Parsear archivo
            df = parser.parse(temp_file)
            assert len(df) == 3
            assert list(df.columns) == ['codigo', 'nombre', 'precio', 'stock']
        
        finally:
            os.unlink(temp_file)
    
    def test_create_parser_for_xlsx(self):
        """Test: Crear parser para archivo XLSX"""
        # Crear archivo temporal XLSX
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
            self.test_data.to_excel(f.name, index=False, engine='openpyxl')
            temp_file = f.name
        
        try:
            # Crear parser
            parser = ExcelParserFactory.create_for_file(temp_file)
            assert parser is not None
            
            # Parsear archivo
            df = parser.parse(temp_file)
            assert len(df) == 3
            assert 'codigo' in df.columns
        
        finally:
            os.unlink(temp_file)
    
    def test_extension_no_soportada(self):
        """Test: Extensión no soportada lanza error"""
        with pytest.raises(ValueError, match="No hay parser disponible"):
            ExcelParserFactory.create_for_file('archivo.json')
    
    def test_get_supported_extensions(self):
        """Test: Obtener extensiones soportadas"""
        extensions = ExcelParserFactory.get_supported_extensions()
        
        assert '.csv' in extensions
        assert '.xlsx' in extensions
        assert '.xls' in extensions
    
    def test_csv_with_special_characters(self):
        """Test: CSV con caracteres especiales (ñ, tildes)"""
        df_special = pd.DataFrame({
            'nombre': ['Niño', 'Año', 'José'],
            'descripción': ['Información', 'Configuración', 'México']
        })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                        delete=False, newline='',
                                        encoding='utf-8') as f:
            df_special.to_csv(f.name, index=False)
            temp_file = f.name
        
        try:
            parser = ExcelParserFactory.create_for_file(temp_file)
            df = parser.parse(temp_file)
            
            assert len(df) == 3
            assert 'Niño' in df['nombre'].values
        
        finally:
            os.unlink(temp_file)


# ============================================
# TESTS DE LLM FACTORY
# ============================================

class TestLLMFactory:
    """Tests para LLMFactory"""
    
    def test_get_available_providers(self):
        """Test: Obtener providers disponibles"""
        providers = LLMFactory.get_available_providers()
        
        assert 'openai' in providers
        assert 'anthropic' in providers
        assert len(providers) >= 2
    
    def test_provider_no_soportado(self):
        """Test: Provider no existente lanza error"""
        with pytest.raises(ValueError, match="no soportado"):
            LLMFactory.create('provider_inexistente', api_key='fake')
    
    def test_create_sin_api_key_falla(self):
        """Test: Crear sin API key lanza error"""
        with pytest.raises(Exception):
            LLMFactory.create('openai')
    
    # NOTA: No hacemos tests que llamen a APIs reales (cuestan dinero)
    # Esos tests los harías en un ambiente de staging con API keys de prueba


# ============================================
# TESTS DE INTEGRACIÓN
# ============================================

class TestFactoriesIntegration:
    """Tests de integración entre factories"""
    
    def test_flujo_completo_excel_a_embeddings(self):
        """Test: Flujo completo - Excel → DataFrame → Embeddings"""
        
        # 1. Crear datos de productos
        productos_df = pd.DataFrame({
            'codigo': ['PROD-001', 'PROD-002'],
            'nombre': ['Laptop HP', 'Mouse Logitech'],
            'descripcion': ['Laptop HP 15 pulgadas', 'Mouse inalámbrico']
        })
        
        # 2. Guardar como CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                        delete=False, newline='') as f:
            productos_df.to_csv(f.name, index=False)
            temp_file = f.name
        
        try:
            # 3. Parsear con ExcelParserFactory
            parser = ExcelParserFactory.create_for_file(temp_file)
            df = parser.parse(temp_file)
            
            assert len(df) == 2
            
            # 4. Generar embeddings con EmbeddingFactory
            generator = EmbeddingFactory.create('local')
            
            embeddings = []
            for idx, row in df.iterrows():
                texto = f"{row['nombre']} {row['descripcion']}"
                embedding = generator.generate(texto)
                embeddings.append(embedding)
            
            # Verificar que se generaron embeddings
            assert len(embeddings) == 2
            assert len(embeddings[0]) == 384  # Dimensión del modelo local
            assert len(embeddings[1]) == 384
            
            # Los embeddings deberían ser diferentes
            assert embeddings[0] != embeddings[1]
        
        finally:
            os.unlink(temp_file)
    
    def test_registro_custom_generator(self):
        """Test: Registrar un generador personalizado"""
        
        # Crear un generador fake para testing
        class FakeGenerator(IEmbeddingGenerator):
            def generate(self, text: str):
                # Siempre retorna el mismo embedding fake
                return [1.0, 2.0, 3.0]
            
            def get_dimension(self):
                return 3
        
        # Registrar
        EmbeddingFactory.register_generator('fake', FakeGenerator)
        
        # Usar
        generator = EmbeddingFactory.create('fake')
        embedding = generator.generate("cualquier texto")
        
        assert embedding == [1.0, 2.0, 3.0]
        assert generator.get_dimension() == 3


# ============================================
# EJECUTAR TESTS
# ============================================

if __name__ == "__main__":
    """Ejecutar tests directamente"""
    pytest.main([__file__, "-v", "--tb=short"])