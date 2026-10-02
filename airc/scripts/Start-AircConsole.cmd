@echo off
REM FR #256: Bypass ExecutionPolicy for unsigned Start-AircConsole.ps1
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%HERE%' -Filter *.ps1 | Unblock-File -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Start-AircConsole.ps1" %*
exit /b %ERRORLEVEL%
