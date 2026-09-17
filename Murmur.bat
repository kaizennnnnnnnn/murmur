@echo off
rem Start Murmur in the background (tray only, no window).
rem Python is resolved in this order: repo-local .venv, then the official py
rem launcher (pyw), then whatever pythonw is on PATH. pyw is preferred over a
rem bare pythonw because PATH often leads to an unrelated venv first.
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" main.py
  goto :eof
)

where pyw.exe >nul 2>&1
if %errorlevel%==0 (
  start "" pyw.exe main.py
  goto :eof
)

start "" pythonw.exe main.py
