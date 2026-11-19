@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Stop Echelon Bridge

pushd "%~dp0"
if errorlevel 1 goto missing_folder
if not exist ".venv\Scripts\python.exe" goto missing_python

".venv\Scripts\python.exe" -m echelon_bridge.windows_launcher --stop
set "bridgeExit=%errorlevel%"
popd
exit /b %bridgeExit%

:missing_python
echo Python dependencies are missing. From this project folder, run:
echo   uv sync --frozen
pause
popd
exit /b 1

:missing_folder
echo Cannot open the folder containing this launcher.
pause
exit /b 1
