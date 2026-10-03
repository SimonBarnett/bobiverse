<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-digest-url-fr354-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #354: Get-BobDigestUrl must not use bob.ntsa.uk /digest

## Problem

Default digest GET pointed at `http://bob.ntsa.uk/bob/v1/digest` (does not resolve; IIS has no `/digest`). Public digest is GET `https://irc.ntsa.uk/bob/v1/report` (`reportUrl`).

## Fix

`Get-BobDigestUrl` order: env → config `digestUrl` → config `reportUrl` → hard default `https://irc.ntsa.uk/bob/v1/report`.

## Tests

`BT354` in `tools/Test-Pack.ps1`
