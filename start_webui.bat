@echo off
chcp 65001 >nul
cd /d "%~dp0"
D:\anaconda\python.exe -m uvicorn src.work_flow.gui.app:app --host 127.0.0.1 --port 8321 --reload
pause

