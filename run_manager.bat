@echo off
title "ZALO BOT MANAGER (Port 9000)"
color 0A
cd /d %~dp0

echo Dang khoi dong Manager API cho Zalo Bot...
if exist venv\Scripts\python.exe (
    venv\Scripts\python.exe manager_api.py
) else (
    python manager_api.py
)
pause
