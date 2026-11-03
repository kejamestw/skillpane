@echo off
setlocal
set "desktopPython=%~dp0.runtime\desktop-build\venv\Scripts\pythonw.exe"
if not exist "%desktopPython%" (
  echo Desktop dependencies are not installed. See docs\DESKTOP.md.
  pause
  exit /b 1
)
start "" "%desktopPython%" -B "%~dp0scripts\desktop_entry.py"
endlocal
