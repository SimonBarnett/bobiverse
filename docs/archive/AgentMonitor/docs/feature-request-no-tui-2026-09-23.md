<!-- ARCHIVED COPY - source: SimonBarnett/AgentMonitor @ 6879d8f, path docs/feature-request-no-tui-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: no tui (issue #22)

https://github.com/SimonBarnett/AgentMonitor/issues/22

**MRB:** [Issue #27](https://github.com/SimonBarnett/AgentMonitor/issues/27) (Bob chairs). **Land:** [PR #23](https://github.com/SimonBarnett/AgentMonitor/pull/23) (`73e86a9`). [PR #26](https://github.com/SimonBarnett/AgentMonitor/pull/26) (`71d0e615`) is a closed duplicate of the same tree as `main`; do not reopen or merge.

Simon paste 2026-09-23, `windows=on`, kind=cursor, cwd=`E:\ai`. No UAT.

## LOCKED (issue #22 log)

1. `--new` pruned four stale cursor-agent nodes and started a watch worker.
2. `create-chat` failed; local session id only.
3. Log said `cursor New: Composer TUI window=Normal` then `cursor TUI agent pid=20688 but Composer node missing (OOM or bad session); stopping agent launcher`.
4. `commitFreeGb=1.85` `cursor-agentNodes=0`.
5. Still logged `started kind=cursor` and `cursor seat: Composer TUI window=Normal`.
6. The operator saw no TUI.

## Gap vs `595e306`

`-Windows on` promises a visible Composer TUI. The script can log Normal and `started` after the Composer node is already gone.

## Acceptance

| ID | Gate |
|----|------|
| A1 | With `-Windows on`, a missing Composer node is not reported as a live Normal TUI. |
| A2 | The watcher console keeps the OOM / missing-node lines. Do not hide that failure. |
| A3 | No UAT stamp. |

UNKNOWN: how much commit flamingo needs; whether `create-chat` must succeed before TUI.
