@echo off
setlocal
if "%~1"=="" (
    echo Usage: %~nx0 grok ^| cursor [new] [off]
    echo   resume: %~nx0 cursor
    echo   new:    %~nx0 cursor new
    echo   extra:  run again while one is live - next free slot, does not restart
    echo   hidden: %~nx0 cursor off
    echo   Visible by default. off hides the watch console and agent TUI.
    exit /b 1
)
set "KIND=%~1"
set "HIDDEN=0"
set "PSARGS=-WatchWorker"
if /i "%KIND%"=="cursor" set "PSARGS=%PSARGS% -Cursor"
if /i "%KIND%"=="grok" set "PSARGS=%PSARGS% -Grok"
if /i not "%KIND%"=="cursor" if /i not "%KIND%"=="grok" (
    echo Unknown kind "%KIND%" - use grok or cursor
    exit /b 1
)
if /i "%~2"=="new" set "PSARGS=%PSARGS% -New"
if /i "%~2"=="off" set "HIDDEN=1"
if /i "%~3"=="new" set "PSARGS=%PSARGS% -New"
if /i "%~3"=="off" set "HIDDEN=1"
if "%HIDDEN%"=="1" (
    set "PSARGS=%PSARGS% -Windows off"
    start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0Watch-AgentHealth.ps1" %PSARGS%
    echo Watch monitor started hidden. Log: %USERPROFILE%\Desktop\Watch-AgentHealth\Watch-AgentHealth.log
    exit /b 0
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0Watch-AgentHealth.ps1" %PSARGS%
exit /b 0
