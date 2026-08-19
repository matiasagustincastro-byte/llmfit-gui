@echo off
REM ---------------------------------------------------------------
REM  LLM Fit GUI - lanzador para Windows (x64 y ARM64)
REM
REM  Camino preferido: uv, que resuelve Python y el wheel de llmfit
REM  de la plataforma sin instalar nada en el sistema.
REM  Sin uv, cae a python + el llmfit que ya tengas instalado.
REM
REM  La ventana se abre desde server.py, cuando el servidor ya esta
REM  escuchando, para que no aparezca un "no se puede conectar".
REM ---------------------------------------------------------------
setlocal
cd /d "%~dp0"

if not defined PORT set "PORT=8080"

where uv >nul 2>&1
if not errorlevel 1 (
  echo [ok] usando uv ^(resuelve Python + llmfit automaticamente^)
  uv run server.py --port %PORT% --app-window
  goto :fin
)

where python >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [!!] No se encontro ni uv ni Python.
  echo.
  echo       Lo mas simple es instalar uv, que se encarga de todo:
  echo         powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  echo.
  pause
  exit /b 1
)

where llmfit >nul 2>&1
if errorlevel 1 (
  echo.
  echo  [!!] Falta el binario llmfit. Instalalo con:
  echo         uv tool install -U llmfit
  echo      o  scoop install llmfit
  echo.
  pause
  exit /b 1
)

python server.py --port %PORT% --app-window

:fin
if errorlevel 1 pause
endlocal
