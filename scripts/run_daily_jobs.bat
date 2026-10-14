@echo off
REM ============================================
REM Script: run_daily_jobs.bat
REM ============================================
REM Ejecuta los jobs diarios del sistema en Windows:
REM 1. Calcular metricas diarias
REM 2. Limpiar conversaciones antiguas (>90 dias)
REM 3. Limpiar metricas antiguas (>1 ano)
REM
REM Uso:
REM   scripts\run_daily_jobs.bat
REM   scripts\run_daily_jobs.bat --date 2026-03-18
REM
REM Programar en Windows Task Scheduler:
REM   schtasks /create /tn "Daily Jobs" /tr "path\to\scripts\run_daily_jobs.bat" /sc daily /st 19:30
REM
REM ============================================

echo.
echo ========================================
echo Ejecutando Jobs Diarios
echo ========================================
echo.

REM Obtener directorio del proyecto
set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"

REM Crear directorio de logs si no existe
if not exist "logs" mkdir logs

REM Obtener fecha para el log
set LOG_DATE=%date:~-4%%date:~3,2%%date:~0,2%
set LOG_TIME=%time:~0,2%%time:~3,2%%time:~6,2%
set LOG_FILE=logs\daily_jobs_%LOG_DATE%.log

echo [%date% %time%] Iniciando jobs diarios >> "%LOG_FILE%"

REM JOB 1: Calcular metricas diarias
echo [*] Calculando metricas diarias...
python scripts\jobs\calculate_metrics.py >> "%LOG_FILE%" 2>&1
if %errorlevel% equ 0 (
    echo     [OK] Metricas calculadas
) else (
    echo     [ERROR] Fallo calculo de metricas
)

REM JOB 2: Limpiar conversaciones antiguas
echo [*] Limpiando conversaciones antiguas...
python scripts\jobs\cleanup_conversations.py --days 90 >> "%LOG_FILE%" 2>&1
if %errorlevel% equ 0 (
    echo     [OK] Conversaciones limpiadas
) else (
    echo     [ERROR] Fallo limpieza conversaciones
)

REM JOB 3: Limpiar metricas antiguas
echo [*] Limpiando metricas antiguas...
python scripts\jobs\cleanup_metrics.py --days 365 >> "%LOG_FILE%" 2>&1
if %errorlevel% equ 0 (
    echo     [OK] Metricas limpiadas
) else (
    echo     [ERROR] Fallo limpieza metricas
)

echo.
echo ========================================
echo Jobs completados
echo ========================================
echo Ver log: %LOG_FILE%

echo [%date% %time%] Jobs completados >> "%LOG_FILE%"
