@echo off
REM Sobe backend (demo, sem Docker) + frontend em duas janelas.
REM Login: erica@demo.local / demo1234 (admin)  |  sdr@demo.local / demo1234
REM Portas 8050/5250 para nao brigar com a copia antiga (omnichannel) em 8000/5173.
setlocal
set ROOT=%~dp0
set API_PORT=8050
set WEB_PORT=5250

REM Python: .venv deste repo; se nao existir, o da copia omnichannel ao lado.
set PY=%ROOT%BackEnd\.venv\Scripts\python.exe
if not exist "%PY%" set PY=%ROOT%..\omnichannel\BackEnd\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo Nao achei o Python do backend. Crie o ambiente uma vez:
  echo   cd BackEnd
  echo   python -m venv .venv
  echo   .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%ROOT%FrontEnd\node_modules\" (
  echo Instalando dependencias do frontend, so na primeira vez...
  pushd "%ROOT%FrontEnd"
  call npm install
  popd
)

REM O backend libera CORS para o painel; o painel aponta para o backend.
set CORS_ALLOWED_ORIGINS=http://127.0.0.1:%WEB_PORT%,http://localhost:%WEB_PORT%
set VITE_API_URL=http://127.0.0.1:%API_PORT%

start "LM Eventos Backend :%API_PORT%" cmd /k "cd /d "%ROOT%BackEnd" && "%PY%" manage.py rundemo 127.0.0.1:%API_PORT% --settings=nucleus.settings_demo"
start "LM Eventos Frontend :%WEB_PORT%" cmd /k "cd /d "%ROOT%FrontEnd" && npm run dev -- --port %WEB_PORT% --host 127.0.0.1 --strictPort"
timeout /t 8 /nobreak >nul
start http://127.0.0.1:%WEB_PORT%
