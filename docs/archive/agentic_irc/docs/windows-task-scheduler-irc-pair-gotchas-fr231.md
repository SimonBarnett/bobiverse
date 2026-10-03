<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/windows-task-scheduler-irc-pair-gotchas-fr231.md, last changed 2026-09-29. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #231: Windows Task Scheduler detached irc_agent/irc_listen gotchas

**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/231  
Harvested from ce-dayworks DEV1 (Windows Server 2022 / PS 5.1).

## Gotchas

1. **Empty DACL on `--home`.** Python `mkdir(mode=0o700)` on Windows can create a directory with explicit non-inherited ACEs; later files (`outbox.txt`) get an empty DACL -> Access Denied. Prefer inheritable owner ACE / skip `0o700` on Windows, or `icacls <home> /grant "<user>:(OI)(CI)F"` then reset children. Upstream `protect.protect_path` already grants `(OI)(CI)(F)` after create - call it on the home directory.
2. **Exe-only `python.exe` under Task Scheduler.** An install without `python3*.dll` beside the exe works interactively (other PATH python) but scheduled tasks exit `0xC0000135` or hang on a hidden hard-error. Pick an interpreter whose folder contains `python3*.dll`.
3. **Hidden-task log capture.** Reliable pattern: `cmd.exe /d /s /c "python -u ... 1>>out.log 2>>err.log"`.
4. **`--stdout-log` age.** Older `irc_listen.py` lacks `--stdout-log`; redirect stdout yourself, or use a checkout that has the flag.

## Working checks
- Listener emits `FROM <nick> <target> <text>`.
- Password only via `AGENTIC_IRC_PASSWORD` (never argv).
