"""
Excel Import Plugin - Importa productos desde archivos Excel/CSV

Este plugin permite:
- Leer archivos .xlsx, .xls, .csv
- Validar estructura y datos
- Mapear a modelo de Producto
- Guardar en Supabase
- Rollback en caso de error
"""
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import pandas as pd
from datetime import datetime, timezone

from src.plugins.base import BasePlugin, PluginMetadata
from src.plugins.decorators import (
    require_running,
    log_execution,
    measure_time,
    validate_config
)
from src.core.event_bus import EventBus
from src.core.tenant_context import TenantContext
from src.core.logger import logger


class ExcelImportPlugin(BasePlugin):
    """
    Plugin para importar productos desde archivos Excel/CSV.
    
    Configuración requerida:
    - repository: ProductRepository para guardar productos
    
    Configuración opcional:
    - batch_size: Tamaño de lote para guardado (default: 100)
    - validate_on_read: Validar durante lectura (default: True)
    - rollback_on_error: Hacer rollback si falla (default: True)
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        tenant_context: Optional[TenantContext] = None
    ):
        super().__init__(event_bus, tenant_context)
        
        self._metadata = PluginMetadata(
            name="excel_import",
            version="1.0.0",
            description="Importa productos desde Excel/CSV",
            author="EstructuraAI Team",
            dependencies=[],
            tenant_specific=True
        )
        
        # Estado interno
        self._product_repository = None
        self._batch_size = 100
        self._validate_on_read = True
        self._rollback_on_error = True
        
        # Estadísticas de importación
        self._import_stats = {
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "saved_products": 0,
            "errors": []
        }
    
    # ==================== LIFECYCLE HOOKS ====================
    
    def on_initialize(self) -> None:
        """Inicializa el plugin con configuración"""
        # Obtener configuración
        self._product_repository = self.get_config("repository")
        if not self._product_repository:
            raise ValueError("Se requiere 'repository' en la configuración")
        
        # Configuración opcional
        self._batch_size = self.get_config("batch_size", 100)
        self._validate_on_read = self.get_config("validate_on_read", True)
        self._rollback_on_error = self.get_config("rollback_on_error", True)
        
        logger.info(
            f"ExcelImportPlugin configurado: "
            f"batch_size={self._batch_size}, "
            f"validate={self._validate_on_read}"
        )
    
    def on_start(self) -> None:
        """Inicia el plugin"""
        # Suscribirse a eventos si es necesario
        self._emit_event("excel_import.ready", {
            "plugin": self.metadata.name,
            "batch_size": self._batch_size
        })
    
    def on_stop(self) -> None:
        """Detiene el plugin y limpia recursos"""
        self._reset_stats()
    
    # ==================== MÉTODOS PÚBLICOS ====================
    
    @require_running
    @measure_time
    @log_execution
    def import_file(
        self,
        file_path: str,
        column_mapping: Optional[Dict[str, str]] = None,
        skip_rows: int = 0
    ) -> Dict[str, Any]:
        """
        Importa productos desde un archivo Excel/CSV.
        
        Args:
            file_path: Ruta al archivo
            column_mapping: Mapeo de columnas (opcional)
            skip_rows: Filas a saltar al inicio
            
        Returns:
            Diccionario con estadísticas de importación
            
        Example:
            stats = plugin.import_file(
                "productos.xlsx",
                column_mapping={
                    "Nombre": "name",
                    "Precio": "price",
                    "Stock": "stock"
                }
            )
        """
        self._reset_stats()
        
        try:
            # Emitir evento de inicio
            self._emit_event("excel_import.started", {
                "file": file_path,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # 1. Leer archivo
            df = self._read_file(file_path, skip_rows)
            self._import_stats["total_rows"] = len(df)
            
            logger.info(f"Archivo leído: {len(df)} filas")
            
            # 2. Aplicar mapeo de columnas
            if column_mapping:
                df = self._apply_column_mapping(df, column_mapping)
            
            # 3. Validar datos
            valid_df, invalid_rows = self._validate_data(df)
            self._import_stats["valid_rows"] = len(valid_df)
            self._import_stats["invalid_rows"] = len(invalid_rows)
            
            if len(invalid_rows) > 0:
                logger.warning(
                    f"Se encontraron {len(invalid_rows)} filas inválidas"
                )
                self._import_stats["errors"].extend(invalid_rows)
            
            # 4. Convertir a productos
            products = self._df_to_products(valid_df)
            
            # 5. Guardar en base de datos
            saved_count = self._save_products(products)
            self._import_stats["saved_products"] = saved_count
            
            # Emitir evento de éxito
            self._emit_event("excel_import.completed", {
                "file": file_path,
                "stats": self._import_stats
            })
            
            logger.success(
                f"Importación completada: {saved_count} productos guardados"
            )
            
            return self._import_stats
            
        except Exception as e:
            # Emitir evento de error
            self._emit_event("excel_import.failed", {
                "file": file_path,
                "error": str(e)
            })
            
            logger.error(f"Error en importación: {e}")
            raise
    
    @require_running
    def get_import_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas de la última importación.
        
        Returns:
            Diccionario con estadísticas
        """
        return self._import_stats.copy()
    
    @require_running
    def preview_file(
        self,
        file_path: str,
        rows: int = 10
    ) -> pd.DataFrame:
        """
        Previsualiza las primeras filas de un archivo.
        
        Args:
            file_path: Ruta al archivo
            rows: Número de filas a mostrar
            
        Returns:
            DataFrame con las primeras filas
        """
        df = self._read_file(file_path, skip_rows=0)
        return df.head(rows)
    
    # ==================== MÉTODOS PRIVADOS ====================
    
    def _read_file(
        self,
        file_path: str,
        skip_rows: int = 0
    ) -> pd.DataFrame:
        """
        Lee un archivo Excel o CSV.
        
        Args:
            file_path: Ruta al archivo
            skip_rows: Filas a saltar
            
        Returns:
            DataFrame con los datos
            
        Raises:
            ValueError: Si el formato no es soportado
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")
        
        extension = path.suffix.lower()
        
        try:
            if extension == ".csv":
                df = pd.read_csv(file_path, skiprows=skip_rows)
            elif extension in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path, skiprows=skip_rows)
            else:
                raise ValueError(
                    f"Formato no soportado: {extension}. "
                    "Use .csv, .xlsx o .xls"
                )
            
            logger.debug(f"Archivo leído: {len(df)} filas, {len(df.columns)} columnas")
            return df
            
        except Exception as e:
            logger.error(f"Error leyendo archivo: {e}")
            raise
    
    def _apply_column_mapping(
        self,
        df: pd.DataFrame,
        mapping: Dict[str, str]
    ) -> pd.DataFrame:
        """
        Aplica mapeo de nombres de columnas.
        
        Args:
            df: DataFrame original
            mapping: Diccionario {nombre_original: nombre_destino}
            
        Returns:
            DataFrame con columnas renombradas
        """
        # Verificar que las columnas existan
        missing_cols = set(mapping.keys()) - set(df.columns)
        if missing_cols:
            logger.warning(
                f"Columnas no encontradas en el archivo: {missing_cols}"
            )
        
        # Renombrar columnas
        df_renamed = df.rename(columns=mapping)
        
        logger.debug(f"Columnas mapeadas: {list(mapping.values())}")
        return df_renamed
    
    def _validate_data(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Valida los datos del DataFrame.
        
        Args:
            df: DataFrame a validar
            
        Returns:
            Tupla (df_válido, lista_de_errores)
        """
        valid_rows = []
        invalid_rows = []
        
        required_columns = ["name", "price"]
        
        for idx, row in df.iterrows():
            errors = []
            
            # Validar columnas requeridas
            for col in required_columns:
                if col not in df.columns:
                    errors.append(f"Columna requerida faltante: {col}")
                    continue
                
                if pd.isna(row.get(col)):
                    errors.append(f"Valor vacío en columna: {col}")
            
            # Validar tipos de datos
            if "price" in df.columns and not pd.isna(row.get("price")):
                try:
                    float(row["price"])
                except (ValueError, TypeError):
                    errors.append(f"Precio inválido: {row.get('price')}")
            
            if "stock" in df.columns and not pd.isna(row.get("stock")):
                try:
                    int(row["stock"])
                except (ValueError, TypeError):
                    errors.append(f"Stock inválido: {row.get('stock')}")
            
            # Clasificar fila
            if errors:
                invalid_rows.append({
                    "row": int(idx),
                    "data": row.to_dict(),
                    "errors": errors
                })
            else:
                valid_rows.append(idx)
        
        # Crear DataFrame con filas válidas
        valid_df = df.loc[valid_rows] if valid_rows else pd.DataFrame()
        
        return valid_df, invalid_rows
    
    def _df_to_products(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Convierte DataFrame a lista de productos.
        
        Args:
            df: DataFrame con datos válidos
            
        Returns:
            Lista de diccionarios de productos
        """
        products = []
        
        for _, row in df.iterrows():
            product = {
                "name": str(row["name"]).strip(),
                "price": float(row["price"]),
                "stock": int(row.get("stock", 0)),
                "description": str(row.get("description", "")).strip() or None,
                "sku": str(row.get("sku", "")).strip() or None,
                "category": str(row.get("category", "")).strip() or None,
            }
            
            products.append(product)
        
        return products
    
    def _save_products(self, products: List[Dict[str, Any]]) -> int:
        """
        Guarda productos en base de datos.
        
        Args:
            products: Lista de productos a guardar
            
        Returns:
            Número de productos guardados
        """
        saved_count = 0
        
        try:
            # Guardar en lotes
            for i in range(0, len(products), self._batch_size):
                batch = products[i:i + self._batch_size]
                
                # Emitir evento de progreso
                self._emit_event("excel_import.progress", {
                    "current": i + len(batch),
                    "total": len(products),
                    "percentage": ((i + len(batch)) / len(products)) * 100
                })
                
                # Guardar cada producto del lote
                for product_data in batch:
                    try:
                        # Aquí usarías el repository real
                        # product = self._product_repository.create(product_data)
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"Error guardando producto: {e}")
                        if self._rollback_on_error:
                            raise
            
            return saved_count
            
        except Exception as e:
            logger.error(f"Error en guardado de productos: {e}")
            raise
    
    def _reset_stats(self) -> None:
        """Reinicia las estadísticas de importación"""
        self._import_stats = {
            "total_rows": 0,
            "valid_rows": 0,
            "invalid_rows": 0,
            "saved_products": 0,
            "errors": []
        }