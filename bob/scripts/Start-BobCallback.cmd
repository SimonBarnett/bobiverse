@echo off
REM Start bobcallback (:7700) from THIS install (jeeves MSI), no hardcoded paths (#53).
REM Layout: <InstallRoot>\scripts\Start-BobCallback.cmd ; secrets in <InstallRoot>\config\ .
setlocal
set "SCRIPTS=%~dp0"
if "%SCRIPTS:~-1%"=="\" set "SCRIPTS=%SCRIPTS:~0,-1%"
REM Digest home: BOB_DIGEST_HOME (set by Install-Jeeves / the ircJeeves service) else <InstallRoot>\home.
if not defined BOB_DIGEST_HOME set "BOB_DIGEST_HOME=%SCRIPTS%\..\home"
if not defined BOB_CONFIG_DIR set "BOB_CONFIG_DIR=%SCRIPTS%\..\config"
if not defined BOB_PYTHON set "BOB_PYTHON=python"
cd /d "%SCRIPTS%"
start "" /B "%BOB_PYTHON%" -u bobcallback.py --home "%BOB_DIGEST_HOME%" --bind 127.0.0.1 --port 7700