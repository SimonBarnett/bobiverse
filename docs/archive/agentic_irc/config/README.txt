# ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path config/README.txt, last changed 2026-09-28. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse).
airc-console release config
===========================

ergo.password is NOT stored in git. Pack-AircConsoleRelease.ps1 embeds it into
the release zip as config/ergo.password from (first match):

  1. env AIRC_PACK_ERGO_PASSWORD or AGENTIC_IRC_PASSWORD
  2. %USERPROFILE%\.grok\ergo\connect.password on the packer box
  3. a local (gitignored) config/ergo.password if you drop one here

Install-AircConsole.ps1 copies that packaged file into
%USERPROFILE%\.airc-console\ergo.password on the client. Target machines do
not need a .grok folder (issue #294).
