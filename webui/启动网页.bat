@echo off
"%SystemRoot%\System32\chcp.com" 65001 >nul
cd /d "%~dp0.."
python -m webui.app
if errorlevel 1 pause
