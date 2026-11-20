@echo off
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境…
  %PY% -m venv .venv
  if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -c "import fastapi,uvicorn" >nul 2>nul
if errorlevel 1 (
  echo 正在安装依赖…
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

echo LocalTV：http://127.0.0.1:8787
echo 关掉这个窗口就会停止。
".venv\Scripts\python.exe" -m localtv
