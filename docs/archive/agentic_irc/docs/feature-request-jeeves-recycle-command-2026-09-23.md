<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-jeeves-recycle-command-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: Jeeves command `!recycle {machine}` (park-only)

**Ask (Simon, 2026-09-23):** Bob does not accept a recycle command.
Feature-request a Jeeves command `!recycle {machinename}`.

**Repo:** https://github.com/SimonBarnett/agentic_irc
**Park-only** until Simon says go. Do not dispatch. No UAT stamp.

## Summary

`!bobiverse` is the digest read, and only Jeeves answers it. There is no
IRC verb that restarts a fleet box. Simon needs Jeeves to accept
`!recycle <machine>` so the named box pulls `agentic_irc`, restarts
its watch seat, and recycles that box's system tray. `bob-*` does not
grow a recycle command of its own.

## Gap vs current tree

- `bobtalk.parse_bobiverse_command` matches `!bobiverse` only.
- `bobreport.HELP_TEXT` lists `!bobiverse`, `!bobiverse <id>`, and
  `!bobiverse ?`. No `!recycle`.
- `irc_agent.Client._answer_bobiverse` whispers a digest. It does not
  start or stop `Watch-Bobiverse`, `Watch-BobTray.ps1`,
  `Install-BobChair.ps1`, or `bobcallback.py`.
- The systray is `agentic_build` `tools/Watch-BobTray.ps1` (NotifyIcon).
  Restart watcher on that script kills every `Watch-BobTray` process for
  the box, rejoins `#bobiverse` via `_Watch-Bobiverse-<id>`, then starts
  exactly one tray. Nothing in `agentic_irc` calls that.
- A query to `bob-ionos` is not a recycle. The watch seat keeps
  announcing `GIT` until that box is actually restarted onto
  `chair-outbox.txt`.

## LOCKED

1. Target repo is `agentic_irc`. Do not change `!bobiverse` behaviour.
2. Command shape is `!recycle <machine>` (one machine token). Jeeves
   (`irc_agent.py --chair`) is the only nick that acts on it. `bob-*`
   and `w-*` do not implement recycle and do not answer the command.
3. `<machine>` is a fleet id: `flamingo`, `marchhare`, `ionos`,
   `ce-priority-dev1`. Alias `dev1` means `ce-priority-dev1`. Any other
   token is refused. No process is stopped.
4. Recycle of a valid machine means, on that box: pull `agentic_irc`,
   restart Watch-Bobiverse (`bob-<id>` from the pulled `irc_agent.py`),
   and recycle the systray. Systray recycle is the existing Restart
   watcher behaviour in `agentic_build` `tools/Watch-BobTray.ps1`: kill
   every `Watch-BobTray` process for that machine, rejoin via
   `_Watch-Bobiverse-<id>`, then start exactly one tray. Do not stop
   `BobFleet-*`. Do not leave a second NotifyIcon up.
5. `!recycle ionos` is the chair home. Besides the watch seat and the
   tray, restart Jeeves (`Install-BobChair.ps1` / `irc_agent.py --chair`)
   and the git webhook listener (`bobcallback.py`) so new `GIT` lines go
   to `chair-outbox.txt` and only Jeeves drains them.
6. No WinRM. No SMB. No secrets in the command, the reply, or git.
7. Talk seats never send `!bobiverse`.

## UNKNOWN

- Who may issue it besides refusing `bob-*` and `w-*` (Halloy `simon`
  only, or any talk seat).
- How Jeeves asks the target box to restart, given WinRM and SMB are
  forbidden. Do not invent a new host or port.
- Reply text and what Jeeves says if the box never confirms.
- `!recycle` with no machine token (error vs chair home).

## Acceptance

- A1: `!recycle ionos` is handled by the chair client only.
- A2: A `bob-*` client does not treat `!recycle` as a command.
- A3: `!bobiverse` tests still pass unchanged.
- A4: An unknown machine is refused and stops nothing.
- A5: Tests cover the parser and the refuse path with no live IRC.
- A6: A valid machine's recycle includes relaunching `Watch-BobTray.ps1`
  on that box (old tray processes gone, one tray left).
