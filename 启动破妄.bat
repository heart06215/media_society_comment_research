@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 破妄 · 评论情感分析平台
set "PORT=5000"
set "URL=http://127.0.0.1:%PORT%/"
set "PY="

if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"

if not defined PY (
  for %%P in (python py) do (
    if not defined PY (
      %%P -c "import flask, flask_cors" >nul 2>nul
      if not errorlevel 1 set "PY=%%P"
    )
  )
)

if not defined PY if exist "D:\python\python.exe" (
  "D:\python\python.exe" -c "import flask, flask_cors" >nul 2>nul
  if not errorlevel 1 set "PY=D:\python\python.exe"
)

if not defined PY goto noenv

call :check >nul 2>nul
if not errorlevel 1 (
  echo %URL% 已经在运行，直接打开浏览器。
  start "" "%URL%"
  exit /b 0
)

echo 解释器：%PY%
echo 服务地址：%URL%
echo 就绪后自动打开浏览器，关掉本窗口即停止服务。
echo.

start "" /B powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "for($i=0;$i -lt 60;$i++){ try{ $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%health'; if($r.StatusCode -eq 200){ Start-Process '%URL%'; exit } }catch{}; Start-Sleep -Milliseconds 800 }" >nul 2>nul

"%PY%" app.py
echo.
echo [服务已退出] 以上为退出前的输出，可截图反馈。
pause
exit /b 0

:check
powershell -NoProfile -ExecutionPolicy Bypass -Command "try{ $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%URL%health'; if($r.StatusCode -eq 200){ exit 0 } }catch{}; exit 1"
exit /b

:noenv
echo [错误] 没有找到安装了 flask 的 Python 解释器。
echo 先在项目目录执行：pip install -r requirements.txt
echo 或者把虚拟环境放到 .venv 目录下，脚本会自动使用。
pause
exit /b 2
