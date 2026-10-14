#!/bin/bash
# ============================================
# Script: run_daily_jobs.sh
# ============================================
# Ejecuta los jobs diarios del sistema:
# 1. Calcular métricas diarias
# 2. Limpiar conversaciones antiguas (>90 días)
# 3. Limpiar métricas antiguas (>1 año)
#
# Uso:
#   ./scripts/run_daily_jobs.sh
#   ./scripts/run_daily_jobs.sh --date 2026-03-17
#
# Configurar cron:
#   crontab -e
#   0 14 * * * /path/to/scripts/run_daily_jobs.sh >> /var/log/daily_jobs.log 2>&1
#
# TAREA 15: Script bash para jobs diarios
# ============================================

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="${PROJECT_DIR}/logs/daily_jobs.log"

# Colores para输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1" | tee -a "$LOG_FILE"
}

# Crear directorio de logs si no existe
mkdir -p "${PROJECT_DIR}/logs"

# Parsear argumentos
DATE_ARG=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --date)
            DATE_ARG="--date $2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Iniciar
log "========================================"
log "🚀 Iniciando jobs diarios"
log "========================================"

# Cambiar al directorio del proyecto
cd "$PROJECT_DIR"

# Activar entorno virtual si existe
if [ -f "${PROJECT_DIR}/venv/bin/activate" ]; then
    source "${PROJECT_DIR}/venv/bin/activate"
elif [ -f "${PROJECT_DIR}/.venv/bin/activate" ]; then
    source "${PROJECT_DIR}/.venv/bin/activate"
fi

# JOB 1: Calcular métricas diarias
log "📊 Job 1: Calculando métricas diarias..."
python scripts/jobs/calculate_metrics.py $DATE_ARG
if [ $? -eq 0 ]; then
    log "✅ Métricas diarias calculadas"
else
    log_error "❌ Error en cálculo de métricas"
fi

# JOB 2: Limpiar conversaciones antiguas
log "🧹 Job 2: Limpiando conversaciones antiguas..."
python scripts/jobs/cleanup_conversations.py --days 90
if [ $? -eq 0 ]; then
    log "✅ Conversaciones antiguas limpiadas"
else
    log_error "❌ Error en limpieza de conversaciones"
fi

# JOB 3: Limpiar métricas antiguas
log "📈 Job 3: Limpiando métricas antiguas..."
python scripts/jobs/cleanup_metrics.py --days 365
if [ $? -eq 0 ]; then
    log "✅ Métricas antiguas limpiadas"
else
    log_error "❌ Error en limpieza de métricas"
fi

# Finalizar
log "========================================"
log "✅ Jobs diarios completados"
log "========================================"

# Desactivar entorno virtual
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi
