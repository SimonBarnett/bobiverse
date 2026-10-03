# ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path third_party/nssm/README.txt, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse).
NSSM (Non-Sucking Service Manager) 2.24
Source: https://nssm.cc/release/nssm-2.24.zip
License: public domain (https://nssm.cc)

Pack-AircConsoleRelease.ps1 / Fetch-Nssm.ps1 download win64\nssm.exe into
this cache (gitignored) and into the release zip under third_party\nssm\win64\
so Install-AircConsole.ps1 works without C:\ai\ergo\nssm.exe (issue #266).
