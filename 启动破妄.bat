@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 破妄 · 评论情感分析平台...
start /B python app.py
timeout /t 4 >nul
start http://localhost:5000