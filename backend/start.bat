@echo off
call .venv\Scripts\activate.bat
uvicorn backend.main:app --reload --port 8000 --log-level debug
pause