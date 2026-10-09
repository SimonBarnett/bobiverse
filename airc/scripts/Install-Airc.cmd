@echo off
REM FR #3685: propagate powershell.exe exit to CAQuietExec (Return=check => msiexec 1603).
REM Also log + outer intake report when Install-Airc.ps1 never runs (#Requires / parse refuse).
setlocal EnableExtensions
set "HERE=%~dp0"
set "LOGDIR=%ProgramData%\Bobiverse\logs"
set "LOG=%LOGDIR%\install-airc.log"
set "FAILFLAG=%LOGDIR%\install-airc-fail-reported.flag"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul

echo %DATE% %TIME% Install-Airc.cmd start args=%*>>"%LOG%" 2>nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%HERE%' -Filter *.ps1 | Unblock-File -ErrorAction SilentlyContinue"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Install-Airc.ps1" %*
set "EC=%ERRORLEVEL%"

if not "%EC%"=="0" (
  echo %DATE% %TIME% Install-Airc.cmd FAIL exit=%EC% args=%*>>"%LOG%" 2>nul
  if exist "%FAILFLAG%" (
    echo %DATE% %TIME% Install-Airc.cmd skip outer report ^(ps1 already reported^)>>"%LOG%" 2>nul
    del /f /q "%FAILFLAG%" 2>nul
  ) else (
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Report-AircInstallCmdFailure.ps1" -ExitCode %EC% -ScriptsDir "%HERE%" -ArgsText "%*"
  )
  exit /b %EC%
)

echo %DATE% %TIME% Install-Airc.cmd ok>>"%LOG%" 2>nul
exit /b 0
