#!/bin/bash
# ============================================
# Script: install_cron.sh
# ============================================
# Instala el cron job para ejecutar jobs diarios a las 2 AM
#
# Uso:
#   bash scripts/install_cron.sh
#   bash scripts/install_cron.sh --remove  # Para remover el cron
#
# TAREA 16: Configurar cron job para ejecutar a las 2 AM
# ============================================

# Configuración
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CRON_FILE="${SCRIPT_DIR}/crontab_config.txt"

# Obtener la ruta absoluta del proyecto
PROJECT_PATH=$(cd "$PROJECT_DIR" && pwd)

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Función de logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

# Verificar si es modo eliminación
REMOVE=false
if [[ "$1" == "--remove" ]]; then
    REMOVE=true
fi

echo "========================================"
echo "🚀 Configuración de Cron Job"
echo "========================================"
echo ""

# Verificar que existe el archivo de jobs
if [ ! -f "${PROJECT_PATH}/scripts/run_daily_jobs.sh" ]; then
    log_error "No se encontró el script run_daily_jobs.sh"
    exit 1
fi

# Verificar que el script sea ejecutable
if [ ! -x "${PROJECT_PATH}/scripts/run_daily_jobs.sh" ]; then
    log "📝 Haciendo ejecutable el script..."
    chmod +x "${PROJECT_PATH}/scripts/run_daily_jobs.sh"
fi

# Crear directorio de logs si no existe
mkdir -p "${PROJECT_PATH}/logs"

# Construir el comando cron (7:30 PM = 19:30)
CRON_CMD="30 19 * * * cd ${PROJECT_PATH} && bash ${PROJECT_PATH}/scripts/run_daily_jobs.sh >> ${PROJECT_PATH}/logs/daily_jobs.log 2>&1"

if [ "$REMOVE" = true ]; then
    # Remover el cron job
    log "🗑️ Removiendo cron job..."
    
    # Obtener crontab actual y filtrar
    crontab -l 2>/dev/null | grep -v "run_daily_jobs.sh" | crontab -
    
    log "✅ Cron job removido"
    exit 0
fi

# Verificar si ya existe el cron job
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -c "run_daily_jobs.sh" || true)

if [ "$EXISTING_CRON" -gt 0 ]; then
    log_warning "⚠️ Ya existe un cron job configurado para daily_jobs"
    log "   Puedes removerlo con: bash scripts/install_cron.sh --remove"
    echo ""
    echo "Cron job actual:"
    crontab -l | grep "run_daily_jobs.sh"
    exit 0
fi

# Agregar el cron job
log "📅 Agregando cron job para ejecutar a las 2:00 AM..."

# Crear entrada de crontab temporal
TEMP_CRON=$(mktemp)
echo "# Jobs diarios - Configurado automáticamente" > "$TEMP_CRON"
echo "$CRON_CMD" >> "$TEMP_CRON"
echo "" >> "$TEMP_CRON"

# Agregar entradas existentes si hay
crontab -l 2>/dev/null | grep -v "run_daily_jobs.sh" >> "$TEMP_CRON" 2>/dev/null

# Instalar nuevo crontab
crontab "$TEMP_CRON"
rm "$TEMP_CRON"

echo ""
log "✅ Cron job instalado correctamente"
echo ""
echo "📋 Configuración:"
echo "   - Script: ${PROJECT_PATH}/scripts/run_daily_jobs.sh"
echo "   - Horario: 7:30 PM (19:30) todos los días"
echo "   - Logs: ${PROJECT_PATH}/logs/daily_jobs.log"
echo ""
echo "📝 Verificar con:"
echo "   crontab -l"
echo ""
echo "🗑️ Para remover:"
echo "   bash scripts/install_cron.sh --remove"
echo ""
echo "========================================"
