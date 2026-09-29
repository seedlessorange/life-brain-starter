@echo off
rem Double-click me once to make the brain run itself every morning at 7:00.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "brain\tools\setup_morning.ps1"
pause
