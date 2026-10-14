"""
Script de Verificación del Setup
=================================

Este script verifica que todo esté configurado correctamente.
Ejecuta: python scripts/test_setup.py
"""

# Importar nuestros módulos
from src.config import settings
from src.core.logger import logger

def verificar_setup():
    """
    Verifica que todo esté funcionando
    """
    logger.info("🚀 Iniciando verificación del setup...")
    
    # 1. Verificar configuración
    logger.info(f"📝 Nombre de la app: {settings.APP_NAME}")
    logger.info(f"🌍 Entorno: {settings.ENVIRONMENT}")
    
    # 2. Verificar entorno virtual
    import sys
    if 'venv' in sys.prefix or 'virtualenv' in sys.prefix:
        logger.success("✅ Entorno virtual activado correctamente")
    else:
        logger.warning("⚠️  No se detectó entorno virtual activado")
    
    # 3. Verificar Python version
    import platform
    python_version = platform.python_version()
    logger.info(f"🐍 Python version: {python_version}")
    
    if python_version >= "3.10":
        logger.success("✅ Versión de Python correcta")
    else:
        logger.error("❌ Se requiere Python 3.10 o superior")
    
    # 4. Verificar dependencias
    try:
        import dotenv
        import loguru
        import pytest
        logger.success("✅ Todas las dependencias instaladas")
    except ImportError as e:
        logger.error(f"❌ Falta instalar dependencia: {e}")
    
    # 5. Verificar estructura de carpetas
    import os
    carpetas_requeridas = [
        'src/core',
        'src/models',
        'src/repositories',
        'src/plugins',
        'src/services',
        'src/api',
        'tests',
        'scripts'
    ]
    
    for carpeta in carpetas_requeridas:
        if os.path.exists(carpeta):
            logger.debug(f"✅ Carpeta existe: {carpeta}")
        else:
            logger.error(f"❌ Carpeta faltante: {carpeta}")
    
    logger.success("🎉 ¡Setup completado exitosamente!")
    logger.info("👉 Ahora estás listo para continuar con el siguiente paso")


if __name__ == "__main__":
    verificar_setup()