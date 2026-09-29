@echo off
REM FR #256 / #305: unsigned downloadable install — Bypass + Unblock-File.
REM Self-elevates via Install-AircConsole.ps1 (UAC) when not already admin.
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%HERE%' -Filter *.ps1 | Unblock-File -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Install-AircConsole.ps1" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" (
  echo ERROR Install-AircConsole failed exit %EC%
  exit /b %EC%
)
echo INFO Install-AircConsole.cmd done
exit /b 0
