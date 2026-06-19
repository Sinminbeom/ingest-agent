@echo off
cd /d "%~dp0"
uv run uvicorn main:app --reload --app-dir src --port 33000
pause
