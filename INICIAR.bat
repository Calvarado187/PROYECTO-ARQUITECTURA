@echo off
cd /d "%~dp0"
echo Abre http://127.0.0.1:8080 y usa el token demo-admin-local
python -m backend.server
pause
