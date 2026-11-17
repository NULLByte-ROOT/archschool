@echo off
chcp 65001 >nul
title ArchSchool - Local Backend (FastAPI + SQLite)
echo ====================================================
echo        Starting ArchSchool Local Backend
echo ====================================================

cd /d "%~dp0"

set "DATABASE_URL=sqlite:///./homework.db"
set "CORS_ORIGINS=*"
set "SECRET_KEY=d638afb33f2145e8a611dd50b6874f72042e83986545457ca5ae2a86ff452ead"
set "ALGORITHM=HS256"
set "ACCESS_TOKEN_EXPIRE_MINUTES=10080"
set "ADMIN_CODE=ROOT01"

echo.
echo [Config]
echo - Database: SQLite (homework.db) [Local & Isolated]
echo - Server:   http://127.0.0.1:8000
echo - Docs:     http://127.0.0.1:8000/docs
echo - Mode:     Development (Auto-reload enabled)
echo ====================================================
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
