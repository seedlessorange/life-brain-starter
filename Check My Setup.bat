@echo off
rem Double-click me to find out what's missing. It only looks and reports.
rem
rem Written for someone who has never opened a terminal, so every failure
rem states the fix in full rather than naming the problem and stopping.
rem
rem NOTE FOR ANYONE EDITING THIS: do not test %errorlevel% inside a
rem parenthesised block. cmd expands %errorlevel% when it parses the whole
rem block, before the command inside has run, so the check silently tests a
rem stale value. The `&&` form below runs the `set` only on success and has
rem no value to expand early.
setlocal
cd /d "%~dp0"
rem Python runs in UTF-8 mode: the self-test prints marks that Windows'
rem older code page cannot write.
set PYTHONUTF8=1

set PYCMD=
set PYSTUB=0
set CLAUDEOK=0
set CLAUDENPM=0
set GITOK=0
set FILESOK=0
set SELFTESTOK=0
set RUNNING=0
set ALLOK=0

rem Python is found by running it, not by looking for the file: Windows
rem puts a "python" on the PATH that only opens the Microsoft Store.
py -3 -c "import sys" >nul 2>nul && set "PYCMD=py -3"
if not defined PYCMD (python -c "import sys" >nul 2>nul && set "PYCMD=python")
if not defined PYCMD (where python >nul 2>nul && set PYSTUB=1)
rem Only the native Windows claude.exe counts. An npm install is a
rem claude.cmd, which the brain will not send prompts through.
where claude.exe >nul 2>nul && set CLAUDEOK=1
if %CLAUDEOK%==0 (where claude.cmd >nul 2>nul && set CLAUDENPM=1)
where git >nul 2>nul && set GITOK=1
if exist "brain\tools\serve.py" set FILESOK=1
netstat -an 2>nul | find "127.0.0.1:7718" | find "LISTENING" >nul 2>nul && set RUNNING=1

echo.
echo   ============================================
echo     Life brain - setup check
echo   ============================================
echo.

if defined PYCMD echo   [ OK ]  Python is installed.
if not defined PYCMD call :nopython

if %CLAUDEOK%==1 echo   [ OK ]  Claude Code is installed.
if %CLAUDENPM%==1 call :claudenpm
if %CLAUDEOK%==0 if %CLAUDENPM%==0 call :noclaude

if %GITOK%==1 echo   [ OK ]  Git is installed (this is your undo button).
if %GITOK%==0 call :nogit

if %FILESOK%==1 echo   [ OK ]  The brain's files are all here.
if %FILESOK%==0 call :nofiles
if %FILESOK%==1 if defined PYCMD call :selftest

if %RUNNING%==1 call :isrunning
if %RUNNING%==0 call :notrunning

if defined PYCMD if %CLAUDEOK%==1 if %GITOK%==1 if %FILESOK%==1 if %SELFTESTOK%==1 set ALLOK=1

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
if %PYSTUB%==1 call :pythonstub
echo.
echo       1. Go to  https://www.python.org/downloads/
echo          and download Python for Windows. It may offer the
echo          "Python install manager" or the classic installer.
echo          Either one works.
echo       2. Run the file it downloads.
echo       3. With the classic installer: ON THE FIRST SCREEN, tick
echo          "Add python.exe to PATH". It is at the bottom and easy
echo          to miss. If you already installed Python without it,
echo          run the installer again and choose Modify.
echo       4. Close this window and run this check again. A window
echo          opened before the install cannot see it.
echo.
exit /b 0

:pythonstub
echo.
echo       Windows has a "python" shortcut that only opens the
echo       Microsoft Store. That shortcut is not a real install.
exit /b 0

:noclaude
echo   [MISSING]  Claude Code
echo.
echo       The page still works without it, but the brain will not
echo       maintain itself.
echo.
echo       Install it from  https://claude.com/claude-code
echo       with the native Windows installer on that page, not npm.
echo.
echo       Already installed it? Close this window, open a NEW one,
echo       and run this check again. A window opened before the
echo       install cannot see it.
echo.
exit /b 0

:claudenpm
echo   [PROBLEM]  Claude Code was installed through npm.
echo.
echo       The brain will not send its prompts through that copy. It
echo       runs through cmd, which cuts a prompt off at its first line
echo       break and can run the rest as commands.
echo.
echo       Install Claude Code again from  https://claude.com/claude-code
echo       with the native Windows installer on that page, not npm.
echo       Then close this window, open a NEW one, and run this check
echo       again.
echo.
exit /b 0

rem The brain ships its own smoke test - checks over the parser, the send
rem boundary and the data files, in about a second with no network and no
rem model. Everything else here proves the machine is ready; this proves
rem the brain itself is.
:selftest
%PYCMD% brain\tools\selftest.py > "%TEMP%\lb-selftest.txt" 2>&1
if %errorlevel%==0 goto selftest_ok
echo   [PROBLEM]  The brain's own checks did not all pass:
echo.
rem The report is UTF-8; show it in UTF-8, then put the window back.
set OLDCP=
for /f "tokens=2 delims=:." %%C in ('chcp') do set "OLDCP=%%C"
chcp 65001 >nul
type "%TEMP%\lb-selftest.txt"
if defined OLDCP chcp %OLDCP% >nul
echo.
echo       Run  claude  in this folder and paste the lines above.
echo.
del "%TEMP%\lb-selftest.txt" >nul 2>nul
exit /b 0
:selftest_ok
set SELFTESTOK=1
for /f "usebackq delims=" %%L in ("%TEMP%\lb-selftest.txt") do set "LASTLINE=%%L"
echo   [ OK ]  %LASTLINE%
del "%TEMP%\lb-selftest.txt" >nul 2>nul
exit /b 0

:nogit
echo   [MISSING]  Git
echo.
echo       The brain needs it on Windows. Claude Code uses it to run
echo       the brain's commands, and it is your undo button: the brain
echo       snapshots your files before and after every job, so a bad
echo       edit can always be reversed.
echo.
echo       Get it from  https://git-scm.com/downloads/win
echo       Accept every default in the installer, then close this
echo       window and run this check again.
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
