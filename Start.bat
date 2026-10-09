@echo off
title Spare Parts Management System
cd /d "%~dp0"
set "PY=%~dp0runtime\python.exe"
if exist "%PY%" goto run
where python >nul 2>nul
if errorlevel 1 goto nopython
set "PY=python"
:run
echo ============================================================
echo   Spare Parts Management System  -  Starting...
echo   First run: a browser will open for initial setup.
echo   Enter the database file location on the shared disk
echo   (all users point to the same database).
echo   Close this window to stop the server.
echo ============================================================
"%PY%" app.py
pause
exit /b 0
:nopython
echo [ERROR] runtime\python.exe not found.
echo Please make sure the "runtime" folder is included.
pause
