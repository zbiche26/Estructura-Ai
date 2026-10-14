@echo off
REM Arranca la API en modo produccion (sin reload)
setlocal

if not exist .env (
  echo [WARN] No se encontro .env en el directorio actual.
)

python -m uvicorn src.http.app:app --host 0.0.0.0 --port 8000

endlocal
