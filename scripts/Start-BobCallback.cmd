@echo off
REM Start bobcallback for IIS ARR (:7700). Safe under LocalSystem airc:
REM load GH_TOKEN from Administrator token file so gh issue create works.
set "USERPROFILE=C:\Users\Administrator"
set "HOMEDRIVE=C:"
set "HOMEPATH=\Users\Administrator"
set "GH_TOKEN="
if exist "C:\Users\Administrator\.grok\bob\github.token" (
  set /p GH_TOKEN=<"C:\Users\Administrator\.grok\bob\github.token"
)
if exist "C:\ai\jeeves\config\github.token" (
  set /p GH_TOKEN=<"C:\ai\jeeves\config\github.token"
)
cd /d C:\ai\jeeves\scripts
start "" /B C:\Python\Python312\python.exe -u bobcallback.py --home C:\Users\Administrator\.agentic-irc-bobiverse --bind 127.0.0.1 --port 7700
