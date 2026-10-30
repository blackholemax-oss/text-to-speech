@echo off
chcp 65001 >nul
cd /d "%~dp0"
set HF_ENDPOINT=https://hf-mirror.com
set FLET_CLIENT_URL=https://gh-proxy.com/https://github.com/flet-dev/flet/releases/download/v1.0.5/flet-windows.zip
".venv\Scripts\flet.exe" run -m app.main
pause
