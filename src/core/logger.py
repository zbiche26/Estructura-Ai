"""
Configuración de Logging
========================

Este archivo configura cómo se verán los mensajes de log en el proyecto.

Ejemplo de uso:
    from src.core.logger import logger
    
    logger.info("Esto es un mensaje informativo")
    logger.warning("Esto es una advertencia")
    logger.error("Esto es un error")
    logger.success("Esto es un éxito")
"""

from loguru import logger
import sys

def setup_logger():
    """
    Configura el sistema de logging
    
    ¿Qué hace?
    - Remueve el logger por defecto de loguru
    - Agrega un nuevo logger con formato personalizado
    - Los logs se muestran en colores en la consola
    """
    
    # Remover configuración por defecto
    logger.remove()
    
    # Formato personalizado de los logs
    # <green>{time:YYYY-MM-DD HH:mm:ss}</green> = Fecha/hora en verde
    # <level>{level: <8}</level> = Nivel del log (INFO, WARNING, etc)
    # <cyan>{name}</cyan>:<cyan>{function}</cyan> = Archivo y función
    # <level>{message}</level> = El mensaje en sí
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Agregar nuevo logger que muestra en consola
    logger.add(
        sys.stdout,              # Mostrar en consola
        format=log_format,       # Usar nuestro formato
        level="DEBUG",           # Mostrar todos los niveles (DEBUG, INFO, WARNING, ERROR)
        colorize=True            # Usar colores
    )
    
    logger.info("✅ Sistema de logging configurado")
    return logger


# Configurar logger al importar este módulo
logger = setup_logger()


# ============================================
# SCRIPT DE PRUEBA
# ============================================

if __name__ == "__main__":
    """
    Prueba todos los niveles de log
    """
    print("\n" + "=" * 50)
    print("PROBANDO SISTEMA DE LOGGING")
    print("=" * 50 + "\n")
    
    logger.debug("🔍 Esto es un mensaje DEBUG (para desarrollo)")
    logger.info("ℹ️  Esto es un mensaje INFO (informativo)")
    logger.warning("⚠️  Esto es un mensaje WARNING (advertencia)")
    logger.error("❌ Esto es un mensaje ERROR (error)")
    logger.success("✅ Esto es un mensaje SUCCESS (éxito)")
    
    print("\n" + "=" * 50)
    print("Los colores ayudan a identificar rápidamente el tipo de mensaje")
    print("=" * 50 + "\n")