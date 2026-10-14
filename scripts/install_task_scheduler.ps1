# ============================================
# Script: install_task_scheduler.ps1
# ============================================
# Instala los jobs diarios en Windows Task Scheduler
# Ejecuta a las 7:30 PM (19:30) todos los dias
#
# Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\install_task_scheduler.ps1
#
# ============================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================"
Write-Host "Configurando Task Scheduler para Jobs Diarios"
Write-Host "========================================"
Write-Host ""

# Ruta del proyecto
$ProjectDir = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectDir "scripts\run_daily_jobs.bat"

# Verificar que existe el script
if (-not (Test-Path $ScriptPath)) {
    Write-Host "[ERROR] No se encontro: $ScriptPath" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Script a ejecutar: $ScriptPath"

# Nombre de la tarea
$TaskName = "ChatbotDailyJobs"

# Verificar si ya existe
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "[!] La tarea '$TaskName' ya existe"
    Write-Host "    Para remover: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:$false"
    Write-Host ""
    Write-Host "Tarea actual:"
    Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo | Select-Object TaskName, LastRunTime, NextRunTime | Format-List
    exit 0
}

# Crear la accion
$Action = New-ScheduledTaskAction -Execute $ScriptPath

# Crear el trigger (7:30 PM todos los dias)
$Trigger = New-ScheduledTaskTrigger -Daily -At "19:30"

# Configuracion
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

# Principal (ejecutar aunque no haya usuario logueado)
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType S4U -RunLevel Limited

# Registrar la tarea
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Ejecuta jobs diarios del chatbot (metricas y limpieza) a las 7:30 PM"

Write-Host ""
Write-Host "[OK] Tarea creada exitosamente" -ForegroundColor Green
Write-Host ""
Write-Host "Configuracion:"
Write-Host "   - Nombre: $TaskName"
Write-Host "   - Horario: 7:30 PM (19:30) diariamente"
Write-Host "   - Script: $ScriptPath"
Write-Host ""
Write-Host "Comandos utiles:"
Write-Host "   Ver tarea:     Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "   Ejecutar ahora: Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "   Remover:       Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
Write-Host ""
Write-Host "========================================"
