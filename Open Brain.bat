@echo off
rem Double-click me to start the brain (Windows).
rem Tries the Python launcher first, then plain python.
cd /d "%~dp0"
rem Same as the Mac launcher: if Tailscale is connected, also serve on the
rem tailnet address so your phone can reach the page. Harmless without it.
set BRAIN_BIND=tailnet
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 brain\tools\serve.py
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python brain\tools\serve.py
    ) else (
        echo.
        echo   Python is not installed, or was installed without "Add to PATH".
        echo   Get it from https://www.python.org/downloads/ and tick
        echo   "Add python.exe to PATH" on the first screen of the installer.
        echo.
        pause
    )
)
rem Keep the window open if the server exits with an error, so the
rem message is readable instead of vanishing.
if %errorlevel% neq 0 pause
