<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-peer-transcript-cpu-fr355-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #355: Import-BobIrcPeerTranscript CPU pin

## Fix

- Walk moot transcript **newest-first**
- Cheap `BOB v1 id=(\S+)` skim; full `ConvertFrom-BobIrcPoint` once per raw id
- Skip import when size+mtime unchanged (script cache)
- `Import-BobIrcTrayPull`: FileStream seek+read (no full-file byte slice)

## Tests

`BT0fr355 peer transcript newest-first + mtime cache` in `tools/Test-Pack.ps1`
