@echo off
rem Double-click me to start the brain (Windows).
rem Tries the Python launcher first, then plain python.
cd /d "%~dp0"
rem Same as the Mac launcher: if Tailscale is connected, also serve on the
rem tailnet address so your phone can reach the page. Harmless without it.
set BRAIN_BIND=tailnet
rem Python runs in UTF-8 mode: Claude's output and the brain's files are
rem UTF-8, and Windows would otherwise use its older code page.
set PYTHONUTF8=1

rem Python is found by running it, not by looking for the file: Windows
rem puts a "python" on the PATH that only opens the Microsoft Store and
rem exits with an error. Labels instead of a bracketed if/else, because cmd
rem reads an errorlevel inside brackets before the command in front of it
rem has run.
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 goto run_py
python -c "import sys" >nul 2>nul
if not errorlevel 1 goto run_python

echo.
echo   Python is not installed, or this window cannot find it.
echo.
echo   Get it from https://www.python.org/downloads/ - the Python install
echo   manager and the classic installer both work. With the classic
echo   installer, tick "Add python.exe to PATH" on its first screen.
echo   Then double-click Open Brain again.
echo.
echo   A "python" that only opens the Microsoft Store is a Windows
echo   shortcut, not a real install.
echo.
pause
exit /b 1

:run_py
py -3 brain\tools\serve.py
goto served

:run_python
python brain\tools\serve.py

:served
rem Keep the window open if the server exits with an error, so the
rem message is readable instead of vanishing.
if %errorlevel% neq 0 pause
