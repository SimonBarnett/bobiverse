<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-invite-airc-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - invite-airc chair one-liner (2026-09-19)

**Repo:** SimonBarnett/agentic_irc  
**Tip:** `978e12a` feat: --chair prints copy-paste thin invite (v0.2.1)  
**Spec:** docs/feature-request-invite-airc-2026-09-19.md  
**Plan:** docs/build-and-test-plan-invite-airc.md  
**Skill:** .grok/skills/invite-airc/SKILL.md  
**UAT log:** docs/invite-airc-uat-2026-09-19.md  
**Machine:** ionos  
**Reviewer:** originating build agent (standing order 2026-09-19) → Bob

## Verdict

**PASS-with-nits** on I1–I7 and plan P0–P3.

Live IONOS chair+thin PIN pair used the printed one-liner; sealed `exec hostname` returned `WIN-MPRE8VI4U6U`. Long-term PSK was not on IRC. Win95 TLS is still not claimed.

**Not** the Bob phrase **ready for human UAT**. Bob owns that stamp. This review recommends granting it for the invite one-liner on Win8+ / Server 2012+ Schannel only.

## Locked gates

| ID | Rule | Disposition |
|---|---|---|
| I1 | Skill `invite-airc` in `.grok/skills/invite-airc/SKILL.md` | **Pass.** Ritual matches. Workaround “compose the line yourself” is gone. |
| I2 | `--chair` stdout includes copy-paste thin line `--pin` `--channel` `--moot` + TTL | **Pass.** Live: `airc-moot-thin.exe --pin REDACTED --channel "#cm-bob-oscar" --moot d3a6414017ede995` plus `expires 10m`. Line has no `INFO` prefix. |
| I3 | Thin happy path is that one line after copying the folder; self-heal nick/home/jail | **Pass coded.** Same-box UAT appended `--nick`/`--home` because two copies cannot share exe-dir/hostname. Walrus USB copy not run. |
| I4 | No long-term PSK on IRC; PIN wrap/GRANT unchanged | **Pass.** Chair/thin logs have no `psk=`. GRANT still AES-256-GCM. Operators after pair: `cm-inv`. |
| I5 | README + agentic-irc / agentic-moot cross-links | **Pass.** Root README table + Mode 3 paragraph; both skills point at `/invite-airc`. |
| I6 | Offline selftest banner contains `--pin` and `--moot` (fixture PIN ok) | **Pass.** `--selftest` prints fixture `482917` banner; pytest asserts tokens. |
| I7 | Win95 TLS not claimed | **Pass.** Usage string, README, OS matrix, skill, this MRB. |

## Plan phases

| Phase | Claim | Evidence |
|---|---|---|
| P0 skill + README | Done | `.grok/skills/invite-airc/SKILL.md`, README, agentic-irc, agentic-moot |
| P1 `--chair` one-liner | Done | `chair_invite_line` / `chair_print_banner` in `pair.c`; live stdout |
| P2 offline selftest | Done | `--selftest` `chair invite banner ok`; `test_chair_invite_line_shape`; 123 passed, 1 skipped |
| P3 UAT + MRB to Bob | Done | docs/invite-airc-uat-2026-09-19.md + this file |

## What was actually run

- Offline: `airc-moot-thin.exe --selftest` (0.2.1, ptr=4); `pytest -q` with `AIRC_MOOT_THIN_EXE`.
- Live: IONOS `#cm-bob-oscar`. Chair `cm-inv --chair --once`. Thin ran the printed command (PIN redacted here). GRANT, `joined as cm-invt … pin=ok`, `operators=cm-inv`. Sealed exec hostname job `5f3f90d778ec59c5` → `WIN-MPRE8VI4U6U`.
- CI Libera: not opened.
- Secrets: live PIN not committed. `connector.key` not committed. Fixture PIN `482917` only in tests/docs.

## Brutal notes (not blockers for this FR)

1. **Same-box is not the field ritual.** The locked operator story is copy-folder-then-one-line. This UAT proved the line on a second nick on the same IP, with extra `--nick`/`--home`. That is allowed by the plan (“second nick or walrus”). It does **not** prove a clueless USB drop onto walrus with zero extra flags.
2. **C chair cannot send DUMB jobs.** Hostname smoke required a Python `irc_agent` as `cm-inv` after `--once` GRANT-exit. Out of scope for this FR (no GUI, no new verb). Do not pretend `--chair` is a full operator console.
3. **`irc_agent.protect_path(home)` vs a raw 32-byte key.** UAT harness hit Win32 ACL denial when Python `icacls /inheritance:r` ran on a home that already held `connector.key`. Product C path is fine. Do not “fix” Mode 1 protect in this ticket.
4. **Rolling release lag.** Immutable tag `airc-moot-thin-v0.2.1` is created only after green `mode3-thin-release.yml`. Operators must not assume GitHub assets already match `978e12a` until that workflow finishes.
5. **Channel quoting.** Invite quotes `"#chan"` for PowerShell. Correct. Operators who strip the quotes in PowerShell will still lose the channel. Skill should keep the quotes (it does).

## Fail bar check

| Fail example | This ticket |
|---|---|
| ok=true without the gate | Hostname JSON has `ok`, `rc`, `stdout`; thin log has the job id |
| Invented APIs | Reused PAIR GRANT / DUMB v1 |
| Breaking prior versions | Mode 1/2 Python untouched; air-gap `--key` still present |
| Secrets in repo | No live PIN, no PSK, no `connector.key` |
| Win95 claim | None |

## Required follow-ups (ordered)

1. **Bob:** stamp or refuse **ready for human UAT** for the invite one-liner on modern Schannel only.
2. **Nit:** confirm GitHub rolling `mode3-thin` / immutable `airc-moot-thin-v0.2.1` after CI.
3. **Nit (optional field):** walrus USB copy with *only* the printed line (no extra `--nick`/`--home`) if Simon wants that row closed.

No ordered product code fixes. Do not reopen PIN wrap/GRANT. Do not add a GUI PIN dialog.

## Non-claims

- Windows 95 / 98 / NT4 / XP live Libera
- Replacement of `--key` air-gap path
- Phase 5 .NET live 2012 smoke
- Bob's **ready for human UAT** phrase (recommended, not stamped here)

## Sign-off

Build-agent hostile MRB → Bob — 2026-09-19 Europe/London — tip `978e12a` — **PASS-with-nits**. Recommend ready for human UAT of invite-airc on Win8+ / Server 2012+ Schannel. Win95 still blocked.
