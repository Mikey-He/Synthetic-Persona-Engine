@echo off
rem Opens a fresh local test session of version A in the browser.
cd /d "%~dp0.."
call npm run open:a
pause
