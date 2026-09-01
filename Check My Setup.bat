@echo off
rem Double-click me to find out what's missing. Reads nothing, changes
rem nothing, installs nothing - it just looks and tells you.
rem
rem Written for someone who has never opened a terminal, so every failure
rem states the fix in full rather than naming the problem and stopping.
rem
rem NOTE FOR ANYONE EDITING THIS: do not put a `where` / `if errorlevel`
rem pair inside a parenthesised block. cmd expands %errorlevel% when it
rem parses the whole block, before the command inside has run, so the
rem check silently tests a stale value. The `&&` form below runs the
rem `set` only on success and has no block to mis-parse.
setlocal
cd /d "%~dp0"

set PYOK=0
set CLAUDEOK=0
set GITOK=0
set FILESOK=0
set RUNNING=0
set ALLOK=0

where py >nul 2>nul && set PYOK=1
if %PYOK%==0 (where python >nul 2>nul && set PYOK=1)
where claude >nul 2>nul && set CLAUDEOK=1
where git >nul 2>nul && set GITOK=1
if exist "brain\tools\serve.py" set FILESOK=1
netstat -an 2>nul | find "127.0.0.1:7718" | find "LISTENING" >nul 2>nul && set RUNNING=1
if %PYOK%==1 if %CLAUDEOK%==1 if %FILESOK%==1 set ALLOK=1

echo.
echo   ============================================
echo     Life brain - setup check
echo   ============================================
echo.

if %PYOK%==1 echo   [ OK ]  Python is installed.
if %PYOK%==0 call :nopython

if %CLAUDEOK%==1 echo   [ OK ]  Claude Code is installed.
if %CLAUDEOK%==0 call :noclaude

if %GITOK%==1 echo   [ OK ]  Git is installed (this is your undo button).
if %GITOK%==0 call :nogit

if %FILESOK%==1 echo   [ OK ]  The brain's files are all here.
if %FILESOK%==0 call :nofiles
if %FILESOK%==1 if %PYOK%==1 call :selftest

if %RUNNING%==1 call :isrunning
if %RUNNING%==0 call :notrunning

echo.
echo   --------------------------------------------
if %ALLOK%==1 call :good
if %ALLOK%==0 call :bad
echo   --------------------------------------------
echo.
pause
exit /b 0

:nopython
echo   [MISSING]  Python
echo.
echo       The page cannot run without it.
echo.
echo       1. Go to  https://www.python.org/downloads/
echo       2. Click the yellow "Download Python" button, run the file.
echo       3. ON THE FIRST SCREEN, tick "Add python.exe to PATH".
echo          It is at the bottom and easy to miss. If you already
echo          installed Python without it, run the installer again
echo          and choose Modify.
echo.
exit /b 0

:noclaude
echo   [MISSING]  Claude Code
echo.
echo       The page still works without it, but the brain will not
echo       maintain itself.
echo.
echo       Install it from  https://claude.com/claude-code
echo       and follow the Windows instructions on that page.
echo.
echo       Already installed it? Close this window, open a NEW one,
echo       and run this check again. A window opened before the
echo       install cannot see it.
echo.
exit /b 0

rem The brain ships its own smoke test - checks over the parser, the send
rem boundary and the data files, in about a second with no network and no
rem model. Everything else here proves the machine is ready; this proves
rem the brain itself is. `py -3` first, matching the launcher.
:selftest
set SELFTEST=
where py >nul 2>nul && set SELFTEST=py -3
if not defined SELFTEST set SELFTEST=python
%SELFTEST% brain\tools\selftest.py > "%TEMP%\lb-selftest.txt" 2>&1
if %errorlevel%==0 goto selftest_ok
echo   [PROBLEM]  The brain's own checks did not all pass:
type "%TEMP%\lb-selftest.txt"
echo.
echo       Run  claude  in this folder and paste the lines above.
echo.
del "%TEMP%\lb-selftest.txt" >nul 2>nul
exit /b 0
:selftest_ok
for /f "usebackq delims=" %%L in ("%TEMP%\lb-selftest.txt") do set LASTLINE=%%L
echo   [ OK ]  %LASTLINE%
del "%TEMP%\lb-selftest.txt" >nul 2>nul
exit /b 0

:nogit
echo   [MISSING]  Git
echo.
echo       Everything still works without it, but you lose the safety
echo       net: the brain snapshots your files before and after every
echo       job, and that is what makes a bad edit undoable.
echo.
echo       Get it from  https://git-scm.com/download/win
echo       Accept every default in the installer.
echo.
echo       (Most people who installed Claude Code already have this.)
echo.
exit /b 0

:nofiles
echo   [PROBLEM]  This folder is incomplete.
echo.
echo       Some files are missing. The usual cause is opening the zip
echo       and running from inside it instead of unzipping first.
echo       Right-click the zip, choose "Extract All", and run this
echo       from the extracted folder.
echo.
exit /b 0

:isrunning
echo   [ OK ]  The page is running right now.
echo             Open  http://127.0.0.1:7718  in your browser.
exit /b 0

:notrunning
echo   [ -- ]  The page is not running.
echo             That is fine - double-click "Open Brain.bat" to
echo             start it whenever you want to use it.
exit /b 0

:good
echo     You are fully set up.
echo.
echo     Next: double-click "Open Brain.bat", then follow Step 4
echo     onward in "START HERE (Windows).md".
exit /b 0

:bad
echo     Fix the items marked MISSING or PROBLEM above, then run
echo     this again.
echo.
echo     The full walkthrough is in "START HERE (Windows).md"
echo     in this folder.
exit /b 0
