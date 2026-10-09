@echo off
REM FR #3685: propagate powershell.exe exit to CAQuietExec (Return=check => msiexec 1603).
REM Also log + outer intake report when Install-Airc.ps1 never runs (#Requires / parse refuse).
REM FR #3759: PS 4.0 -File can exit 0 after a script throw; treat fail-reported.flag as FAIL too.
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

REM FR #3759: if ps1 reported failure but -File still returned 0 (PS 4.0 throw), force FAIL.
if "%EC%"=="0" if exist "%FAILFLAG%" (
  echo %DATE% %TIME% Install-Airc.cmd FR3759 fail-flag present with EC=0 - treating as FAIL>>"%LOG%" 2>nul
  set "EC=1"
)

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

REM FR #3759: never leave a stale fail flag after a claimed ok path.
if exist "%FAILFLAG%" del /f /q "%FAILFLAG%" 2>nul
echo %DATE% %TIME% Install-Airc.cmd ok>>"%LOG%" 2>nul
exit /b 0
