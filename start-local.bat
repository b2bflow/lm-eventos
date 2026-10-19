@echo off
REM Sobe backend (demo, sem Docker) + frontend em duas janelas.
REM Login: erica / demo1234 (admin)  |  sdr / demo1234
set ROOT=%~dp0
start "LM Backend :8000" cmd /k "cd /d %ROOT%BackEnd && .venv\Scripts\python.exe manage.py rundemo 127.0.0.1:8000 --settings=nucleus.settings_demo"
start "LM Frontend :5173" cmd /k "cd /d %ROOT%FrontEnd && npm run dev -- --port 5173 --host 127.0.0.1"
timeout /t 8 /nobreak >nul
start http://127.0.0.1:5173
