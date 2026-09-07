@echo off
setlocal
 title Discord Crystal Bot
pushd "%~dp0"
if errorlevel 1 goto directory_error

if not exist ".venv\Scripts\python.exe" goto python_missing
if not exist "bot.py" goto bot_missing

echo Starting Discord Bot...
echo Press Ctrl+C to stop the bot.
echo.
".venv\Scripts\python.exe" "bot.py" %*
set "BOT_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Bot stopped. Exit code: %BOT_EXIT_CODE%
popd
pause
exit /b %BOT_EXIT_CODE%

:python_missing
echo ERROR: .venv\Scripts\python.exe was not found.
echo Follow the Windows setup instructions in README.md first.
popd
pause
exit /b 1

:bot_missing
echo ERROR: bot.py was not found beside this launcher.
popd
pause
exit /b 1

:directory_error
echo ERROR: Cannot open the bot project directory.
pause
exit /b 1
