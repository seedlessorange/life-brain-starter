@echo off
rem Double-click me once to schedule the night shift: the heavy jobs run at
rem 1am while you're asleep, so they aren't competing with your day for the
rem same five-hour usage allowance.
rem
rem This only registers the schedule. It stays switched OFF until you turn
rem it on from the page (the "Night shift" row under Talk to Claude), so
rem double-clicking this by accident costs nothing.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "brain\tools\setup_night.ps1"
rem If the setup stopped with a message, leave that message as the last word.
if errorlevel 1 goto done
echo.
echo   Next: open the page and click "Turn on" next to Night shift.
:done
echo.
pause
