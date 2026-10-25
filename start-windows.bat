@echo off
REM SolarPulse one-click setup + start (Windows). Double-click this file.
cd /d "%~dp0"
echo === SolarPulse setup (first run takes a minute) ===
where py >nul 2>nul
if %errorlevel%==0 (set "PY=py") else (set "PY=python")
%PY% --version >nul 2>nul
if errorlevel 1 goto nopython
where npm >nul 2>nul
if errorlevel 1 goto nonode
if not exist backend\.venv %PY% -m venv backend\.venv
if errorlevel 1 goto err
backend\.venv\Scripts\python.exe -m pip install -q --upgrade pip
backend\.venv\Scripts\python.exe -m pip install -q -r backend\requirements.txt
if errorlevel 1 goto err
if not exist frontend\.env.local copy frontend\.env.example frontend\.env.local >nul
pushd frontend
call npm install --no-audit --no-fund
if errorlevel 1 goto err
popd
start "SolarPulse API" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
start "SolarPulse Web" cmd /k "cd /d %~dp0frontend && npm run dev"
echo Opening http://localhost:3000 in a few seconds...
timeout /t 10 >nul
start http://localhost:3000
goto :eof
:nopython
echo Python 3.10+ is required: https://www.python.org/downloads/  (tick "Add python.exe to PATH")
pause
goto :eof
:nonode
echo Node.js 20.9+ is required: https://nodejs.org/
pause
goto :eof
:err
echo Something failed - read the message above, then see Troubleshooting in README.md
pause
