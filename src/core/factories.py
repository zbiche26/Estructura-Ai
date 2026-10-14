"""
Factory Pattern - Creación Flexible de Objetos
===============================================

Este módulo implementa el patrón Factory para crear diferentes
tipos de objetos de forma flexible y extensible.

Factories implementadas:
- EmbeddingFactory: Crea generadores de embeddings (OpenAI, Local)
- ExcelParserFactory: Crea parsers de Excel/CSV según extensión
- LLMFactory: Crea clientes de LLM (OpenAI, Anthropic)

Ventajas del Factory Pattern:
- Código cliente no necesita conocer las clases concretas
- Fácil agregar nuevos providers sin modificar código existente
- Centraliza la lógica de creación de objetos

Ejemplo de uso:
    # Crear generador de embeddings
    generator = EmbeddingFactory.create('openai', api_key='sk-...')
    embedding = generator.generate('Laptop HP 15')
    
    # Cambiar provider es trivial
    generator = EmbeddingFactory.create('local')
    embedding = generator.generate('Laptop HP 15')
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import pandas as pd
from pathlib import Path
from src.core.logger import logger


# ============================================
# INTERFACES BASE (Contratos)
# ============================================

class IEmbeddingGenerator(ABC):
    """
    Interfaz para generadores de embeddings
    
    Un embedding es una representación vectorial de texto
    que captura su significado semántico.
    
    Ejemplo: "laptop" y "computadora" tendrán embeddings similares
    """
    
    @abstractmethod
    def generate(self, text: str) -> List[float]:
        """
        Genera embedding para un texto
        
        Args:
            text: Texto a convertir en embedding
        
        Returns:
            Lista de números (vector) que representa el texto
        
        Example:
            embedding = generator.generate("Laptop HP 15")
            # [0.234, -0.567, 0.123, ..., 0.456]  (1536 números)
        """
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """
        Retorna la dimensión del embedding
        
        Returns:
            Número de dimensiones (ej: 1536 para OpenAI)
        """
        pass


class IExcelParser(ABC):
    """
    Interfaz para parsers de archivos Excel/CSV
    """
    
    @abstractmethod
    def parse(self, file_path: str) -> pd.DataFrame:
        """
        Parsea archivo y retorna DataFrame
        
        Args:
            file_path: Ruta al archivo
        
        Returns:
            DataFrame de pandas con los datos
        """
        pass
    
    @abstractmethod
    def supports_extension(self, extension: str) -> bool:
        """
        Verifica si este parser soporta la extensión
        
        Args:
            extension: Extensión del archivo (ej: '.xlsx')
        
        Returns:
            True si soporta, False si no
        """
        pass


class ILLMClient(ABC):
    """
    Interfaz para clientes de LLM (Large Language Model)
    """
    
    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 1000, 
                temperature: float = 0.7) -> str:
        """
        Genera texto usando el LLM
        
        Args:
            prompt: Texto de entrada (instrucción para el LLM)
            max_tokens: Máximo de tokens a generar
            temperature: Creatividad (0 = determinista, 1 = creativo)
        
        Returns:
            Texto generado por el LLM
        """
        pass
    
    @abstractmethod
    def generate_with_history(self, messages: List[Dict[str, str]], 
                              max_tokens: int = 1000,
                              temperature: float = 0.7) -> str:
        """
        Genera texto considerando historial de conversación
        
        Args:
            messages: Lista de mensajes [{"role": "user", "content": "..."}]
            max_tokens: Máximo de tokens
            temperature: Creatividad
        
        Returns:
            Respuesta del LLM
        """
        pass


# ============================================
# 1. EMBEDDING GENERATORS (Implementaciones)
# ============================================

class OpenAIEmbeddingGenerator(IEmbeddingGenerator):
    """Generador de embeddings usando OpenAI"""
    
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        """
        Inicializa generador de OpenAI
        
        Args:
            api_key: API key de OpenAI
            model: Modelo a usar (text-embedding-3-small es más barato)
        """
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"🤖 OpenAI Embedding Generator inicializado (modelo: {model})")
    
    def generate(self, text: str) -> List[float]:
        """Genera embedding usando OpenAI"""
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            embedding = response.data[0].embedding
            logger.debug(f"✅ Embedding generado: {len(embedding)} dimensiones")
            return embedding
        
        except Exception as e:
            logger.error(f"❌ Error generando embedding con OpenAI: {e}")
            raise
    
    def get_dimension(self) -> int:
        """text-embedding-3-small tiene 1536 dimensiones"""
        return 1536


class LocalEmbeddingGenerator(IEmbeddingGenerator):
    """Generador de embeddings local (sin costo, sin API)"""
    
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Inicializa generador local
        
        Args:
            model_name: Modelo de HuggingFace a usar
        
        Note:
            La primera vez descargará el modelo (~80MB)
            Luego lo usará desde cache (gratis, sin API)
        """
        from sentence_transformers import SentenceTransformer
        
        logger.info(f"📥 Cargando modelo local: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.success("✅ Modelo local cargado")
    
    def generate(self, text: str) -> List[float]:
        """Genera embedding localmente"""
        try:
            embedding = self.model.encode(text)
            logger.debug(f"✅ Embedding local generado: {len(embedding)} dimensiones")
            return embedding.tolist()
        
        except Exception as e:
            logger.error(f"❌ Error generando embedding local: {e}")
            raise
    
    def get_dimension(self) -> int:
        """all-MiniLM-L6-v2 tiene 384 dimensiones"""
        return 384


# ============================================
# 2. EXCEL PARSERS (Implementaciones)
# ============================================

class XLSXParser(IExcelParser):
    """Parser para archivos Excel modernos (.xlsx)"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """Parsea archivo .xlsx"""
        try:
            logger.info(f"📊 Parseando archivo XLSX: {Path(file_path).name}")
            df = pd.read_excel(file_path, engine='openpyxl')
            logger.success(f"✅ Archivo parseado: {len(df)} filas, {len(df.columns)} columnas")
            return df
        
        except Exception as e:
            logger.error(f"❌ Error parseando XLSX: {e}")
            raise
    
    def supports_extension(self, extension: str) -> bool:
        return extension.lower() == '.xlsx'


class XLSParser(IExcelParser):
    """Parser para archivos Excel antiguos (.xls)"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """Parsea archivo .xls"""
        try:
            logger.info(f"📊 Parseando archivo XLS: {Path(file_path).name}")
            df = pd.read_excel(file_path, engine='xlrd')
            logger.success(f"✅ Archivo parseado: {len(df)} filas")
            return df
        
        except Exception as e:
            logger.error(f"❌ Error parseando XLS: {e}")
            raise
    
    def supports_extension(self, extension: str) -> bool:
        return extension.lower() == '.xls'


class CSVParser(IExcelParser):
    """Parser para archivos CSV"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """Parsea archivo CSV"""
        try:
            logger.info(f"📊 Parseando archivo CSV: {Path(file_path).name}")
            
            # Intentar diferentes encodings comunes
            encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            
            for encoding in encodings:
                try:
                    df = pd.read_csv(file_path, encoding=encoding)
                    logger.success(f"✅ CSV parseado con encoding {encoding}: {len(df)} filas")
                    return df
                except UnicodeDecodeError:
                    continue
            
            # Si ninguno funcionó, lanzar error
            raise ValueError(f"No se pudo detectar el encoding del CSV: {file_path}")
        
        except Exception as e:
            logger.error(f"❌ Error parseando CSV: {e}")
            raise
    
    def supports_extension(self, extension: str) -> bool:
        return extension.lower() == '.csv'


# ============================================
# 3. LLM CLIENTS (Implementaciones)
# ============================================

class OpenAIClient(ILLMClient):
    """Cliente para OpenAI (GPT-4, GPT-3.5)"""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        """
        Inicializa cliente OpenAI
        
        Args:
            api_key: API key de OpenAI
            model: Modelo (gpt-4o, gpt-4o-mini, gpt-3.5-turbo)
        """
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
        logger.info(f"🤖 OpenAI Client inicializado (modelo: {model})")
    
    def generate(self, prompt: str, max_tokens: int = 1000, 
                temperature: float = 0.7) -> str:
        """Genera respuesta simple"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"❌ Error en OpenAI: {e}")
            raise
    
    def generate_with_history(self, messages: List[Dict[str, str]], 
                              max_tokens: int = 1000,
                              temperature: float = 0.7) -> str:
        """Genera respuesta con historial"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        
        except Exception as e:
            logger.error(f"❌ Error en OpenAI: {e}")
            raise


class AnthropicClient(ILLMClient):
    """Cliente para Anthropic Claude"""
    
    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022"):
        """
        Inicializa cliente Anthropic
        
        Args:
            api_key: API key de Anthropic
            model: Modelo de Claude
        """
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.model = model
        logger.info(f"🤖 Anthropic Client inicializado (modelo: {model})")
    
    def generate(self, prompt: str, max_tokens: int = 1000,
                temperature: float = 0.7) -> str:
        """Genera respuesta simple"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        
        except Exception as e:
            logger.error(f"❌ Error en Anthropic: {e}")
            raise
    
    def generate_with_history(self, messages: List[Dict[str, str]],
                              max_tokens: int = 1000,
                              temperature: float = 0.7) -> str:
        """Genera respuesta con historial"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages
            )
            return response.content[0].text
        
        except Exception as e:
            logger.error(f"❌ Error en Anthropic: {e}")
            raise
# ============================================
# FACTORIES (Creadores de Objetos)
# ============================================

class EmbeddingFactory:
    """
    Factory para crear generadores de embeddings
    
    Permite cambiar fácilmente entre diferentes providers
    sin modificar el código que usa embeddings.
    
    Usage:
        # Usar OpenAI
        generator = EmbeddingFactory.create('openai', api_key='sk-...')
        embedding = generator.generate('Laptop HP')
        
        # Cambiar a local (gratis)
        generator = EmbeddingFactory.create('local')
        embedding = generator.generate('Laptop HP')
    """
    
    _generators = {
        'openai': OpenAIEmbeddingGenerator,
        'local': LocalEmbeddingGenerator
    }
    
    @classmethod
    def create(cls, provider: str, **kwargs) -> IEmbeddingGenerator:
        """
        Crea un generador de embeddings
        
        Args:
            provider: 'openai' o 'local'
            **kwargs: Argumentos específicos del provider
                     - openai: api_key, model
                     - local: model_name
        
        Returns:
            Generador de embeddings
        
        Raises:
            ValueError: Si el provider no existe
        
        Example:
            # OpenAI
            gen = EmbeddingFactory.create('openai', 
                                         api_key='sk-...',
                                         model='text-embedding-3-small')
            
            # Local
            gen = EmbeddingFactory.create('local',
                                         model_name='all-MiniLM-L6-v2')
        """
        if provider not in cls._generators:
            raise ValueError(
                f"Provider '{provider}' no soportado. "
                f"Disponibles: {list(cls._generators.keys())}"
            )
        
        generator_class = cls._generators[provider]
        logger.info(f"🏭 Creando embedding generator: {provider}")
        
        try:
            return generator_class(**kwargs)
        except Exception as e:
            logger.error(f"❌ Error creando generator '{provider}': {e}")
            raise
    
    @classmethod
    def register_generator(cls, name: str, generator_class: type):
        """
        Registra un nuevo tipo de generador
        
        Args:
            name: Nombre del provider
            generator_class: Clase que implementa IEmbeddingGenerator
        
        Example:
            class MiGenerador(IEmbeddingGenerator):
                # ... implementación ...
            
            EmbeddingFactory.register_generator('mi_provider', MiGenerador)
        """
        cls._generators[name] = generator_class
        logger.info(f"✅ Generator '{name}' registrado")
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Retorna lista de providers disponibles"""
        return list(cls._generators.keys())


class ExcelParserFactory:
    """
    Factory para crear parsers de Excel/CSV
    
    Detecta automáticamente el formato del archivo
    y crea el parser apropiado.
    
    Usage:
        parser = ExcelParserFactory.create_for_file('productos.xlsx')
        df = parser.parse('productos.xlsx')
    """
    
    _parsers = [
        XLSXParser(),
        XLSParser(),
        CSVParser()
    ]
    
    @classmethod
    def create_for_file(cls, file_path: str) -> IExcelParser:
        """
        Crea el parser apropiado para un archivo
        
        Args:
            file_path: Ruta al archivo
        
        Returns:
            Parser apropiado para el archivo
        
        Raises:
            ValueError: Si no hay parser para la extensión
        
        Example:
            # Detecta automáticamente que es .xlsx
            parser = ExcelParserFactory.create_for_file('productos.xlsx')
            df = parser.parse('productos.xlsx')
        """
        # Obtener extensión del archivo
        path = Path(file_path)
        extension = path.suffix
        
        # Buscar parser que soporte esta extensión
        for parser in cls._parsers:
            if parser.supports_extension(extension):
                logger.info(
                    f"🏭 Parser seleccionado para '{extension}': "
                    f"{parser.__class__.__name__}"
                )
                return parser
        
        # No se encontró parser
        raise ValueError(
            f"No hay parser disponible para extensión '{extension}'. "
            f"Soportados: .xlsx, .xls, .csv"
        )
    
    @classmethod
    def register_parser(cls, parser: IExcelParser):
        """
        Registra un nuevo parser
        
        Args:
            parser: Instancia del parser
        
        Example:
            class JSONParser(IExcelParser):
                # ... implementación ...
            
            ExcelParserFactory.register_parser(JSONParser())
        """
        cls._parsers.append(parser)
        logger.info(f"✅ Parser registrado: {parser.__class__.__name__}")
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """Retorna lista de extensiones soportadas"""
        extensions = []
        for ext in ['.xlsx', '.xls', '.csv']:
            for parser in cls._parsers:
                if parser.supports_extension(ext):
                    extensions.append(ext)
                    break
        return extensions


class LLMFactory:
    """
    Factory para crear clientes de LLM
    
    Permite cambiar fácilmente entre OpenAI y Anthropic
    (o agregar nuevos providers en el futuro).
    
    Usage:
        llm = LLMFactory.create('openai', api_key='sk-...')
        response = llm.generate('Hola, ¿cómo estás?')
    """
    
    _clients = {
        'openai': OpenAIClient,
        'anthropic': AnthropicClient
    }
    
    @classmethod
    def create(cls, provider: str, **kwargs) -> ILLMClient:
        """
        Crea un cliente de LLM
        
        Args:
            provider: 'openai' o 'anthropic'
            **kwargs: Argumentos específicos del provider
                     - api_key: API key (requerido)
                     - model: Modelo a usar (opcional)
        
        Returns:
            Cliente de LLM
        
        Raises:
            ValueError: Si el provider no existe
        
        Example:
            # OpenAI
            llm = LLMFactory.create('openai', 
                                   api_key='sk-...',
                                   model='gpt-4o-mini')
            
            # Anthropic
            llm = LLMFactory.create('anthropic',
                                   api_key='sk-ant-...',
                                   model='claude-3-5-sonnet-20241022')
        """
        if provider not in cls._clients:
            raise ValueError(
                f"Provider '{provider}' no soportado. "
                f"Disponibles: {list(cls._clients.keys())}"
            )
        
        client_class = cls._clients[provider]
        logger.info(f"🏭 Creando LLM client: {provider}")
        
        try:
            return client_class(**kwargs)
        except Exception as e:
            logger.error(f"❌ Error creando LLM client '{provider}': {e}")
            raise
    
    @classmethod
    def register_client(cls, name: str, client_class: type):
        """
        Registra un nuevo tipo de cliente LLM
        
        Args:
            name: Nombre del provider
            client_class: Clase que implementa ILLMClient
        """
        cls._clients[name] = client_class
        logger.info(f"✅ LLM client '{name}' registrado")
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Retorna lista de providers disponibles"""
        return list(cls._clients.keys())


# ============================================
# SCRIPT DE PRUEBA
# ============================================

if __name__ == "__main__":
    """
    Script de prueba de las factories
    """
    
    logger.info("=" * 60)
    logger.info("🧪 PROBANDO FACTORIES")
    logger.info("=" * 60)
    
    # ========================================
    # TEST 1: EMBEDDING FACTORY (LOCAL)
    # ========================================
    logger.info("\n1️⃣  Test: EmbeddingFactory (Local)")
    try:
        # Usar embeddings locales (gratis, sin API)
        generator = EmbeddingFactory.create('local')
        
        # Generar embedding
        text = "Laptop HP 15 pulgadas con 8GB RAM"
        embedding = generator.generate(text)
        
        logger.success(f"✅ Embedding generado: {len(embedding)} dimensiones")
        logger.info(f"📊 Primeros 5 valores: {embedding[:5]}")
        
        # Verificar dimensión
        dimension = generator.get_dimension()
        logger.info(f"📏 Dimensión: {dimension}")
        
    except Exception as e:
        logger.error(f"❌ Error en test 1: {e}")
    
    # ========================================
    # TEST 2: EXCEL PARSER FACTORY
    # ========================================
    logger.info("\n2️⃣  Test: ExcelParserFactory")
    try:
        # Crear DataFrame de prueba
        import tempfile
        
        df_test = pd.DataFrame({
            'codigo': ['PROD-001', 'PROD-002'],
            'nombre': ['Laptop HP', 'Mouse Logitech'],
            'precio': [850.00, 25.50],
            'stock': [10, 50]
        })
        
        # Guardar como CSV temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', 
                                        delete=False, newline='') as f:
            df_test.to_csv(f.name, index=False)
            temp_file = f.name
        
        # Crear parser automáticamente
        parser = ExcelParserFactory.create_for_file(temp_file)
        
        # Parsear
        df_parsed = parser.parse(temp_file)
        
        logger.success(f"✅ Archivo parseado: {len(df_parsed)} filas")
        logger.info(f"📊 Columnas: {list(df_parsed.columns)}")
        
        # Limpiar archivo temporal
        import os
        os.unlink(temp_file)
        
        # Mostrar extensiones soportadas
        extensions = ExcelParserFactory.get_supported_extensions()
        logger.info(f"📋 Extensiones soportadas: {extensions}")
        
    except Exception as e:
        logger.error(f"❌ Error en test 2: {e}")
    
    # ========================================
    # TEST 3: LLM FACTORY (SIMULAR)
    # ========================================
    logger.info("\n3️⃣  Test: LLMFactory (providers disponibles)")
    try:
        providers = LLMFactory.get_available_providers()
        logger.info(f"🤖 LLM Providers disponibles: {providers}")
        
        # No vamos a hacer llamadas reales (cuestan dinero)
        logger.info("💡 Para usar, necesitas configurar API keys en .env")
        
    except Exception as e:
        logger.error(f"❌ Error en test 3: {e}")
    
    # ========================================
    # RESUMEN
    # ========================================
    logger.info("\n" + "=" * 60)
    logger.success("🎉 ¡FACTORIES FUNCIONANDO!")
    logger.info("=" * 60)
    
    logger.info("\n📚 Cómo usar en tu código:")
    logger.info("""
    # Embeddings
    gen = EmbeddingFactory.create('local')
    embedding = gen.generate('texto')
    
    # Excel
    parser = ExcelParserFactory.create_for_file('productos.xlsx')
    df = parser.parse('productos.xlsx')
    
    # LLM (cuando tengas API key)
    llm = LLMFactory.create('openai', api_key='sk-...')
    response = llm.generate('Hola')
    """)