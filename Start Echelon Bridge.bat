@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Echelon Bridge

rem Always read .env and use the environment beside this batch file.
pushd "%~dp0"
if errorlevel 1 goto missing_folder
if not exist ".venv\Scripts\python.exe" goto missing_python
if not exist "backend\frontend_dist\index.html" goto missing_dashboard

".venv\Scripts\python.exe" -m echelon_bridge.windows_launcher
set "bridgeExit=%errorlevel%"
popd
exit /b %bridgeExit%

:missing_python
echo Python dependencies are not installed. From this project folder, run:
echo   uv sync --frozen
goto setup_failed

:missing_dashboard
echo The dashboard has not been built. From this project folder, run:
echo   npm.cmd --prefix frontend ci
echo   npm.cmd --prefix frontend run build
goto setup_failed

:setup_failed
echo.
pause
popd
exit /b 1

:missing_folder
echo Cannot open the folder containing this launcher.
pause
exit /b 1
