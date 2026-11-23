# FR #9242: jeeves PyInstaller import MemoryError

## Symptom (walrus 2026-11-23)

`jeeves.exe` crash-sig `dcffcd163f9b6192`:

`MemoryError: Unable to allocate output buffer` inside `pyimod01_archive.extract`
while `import irc_agent` ran from `jeeves_main.main` (frozen build 1.0.8).

## Fix

`import_heavy(name)` retries the import once after `gc.collect()`. Persistent OOM
on `bobcallback` / `irc_agent` (and the chair try) returns exit code **1** so NSSM
`AppExit Default Restart` can recover after host RAM frees. Does not invent tokens
or change IRC/HTTP behaviour on success.

## Test isolation (FR #9291)

`jeeves_main.main(--chair)` sets `BOB_DIGEST_HOME` / `BOB_HOME` for the process.
Pytest coverage of the OOM exit path must `monkeypatch.setenv` those keys **before**
calling `main` so undo clears them afterward. A bare `delenv(..., raising=False)`
when the key is absent registers no undo; the leaked tmp home then makes
`fleet_digest_home` redirect later suite tests (webhooks roster 403, queue append).