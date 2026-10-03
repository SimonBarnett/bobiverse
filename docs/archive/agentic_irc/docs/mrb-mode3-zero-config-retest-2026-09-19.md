<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/mrb-mode3-zero-config-retest-2026-09-19.md, last changed 2026-09-25. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB - Mode 3 zero-config PIN onboarding (2026-09-19)

**Tip:** 2b1d743 feat: Mode 3 zero-config PIN onboarding (v0.2.0)
**Prior FAIL plan:** docs/mrb-mode3-zero-config-2026-09-19.md / af6f0c8
**Job:** ionos 38870871

## Verdict

**PASS-with-nits** for engineering P0-P3 offline.
**Not ready for human UAT** of the PIN/double-click path until a live chair+thin PIN smoke (IONOS or walrus) is logged.

Prior Mode 3 UAT (flag/`--config` + shared key) on IONOS/walrus remains valid for Schannel exec. This ticket is the UX layer on top.

## Evidence

| Check | Result |
|---|---|
| VERSION | 0.2.0 |
| docs/mode3-zero-config-2026-09-19.md | Present (Z0-Z8, crypto sketch) |
| `--selftest` | ok: self-heal, pin wrap, mismatch refuse, pair grant, sibling ini |
| pytest -q | **122 passed, 1 skipped** |
| Mode 1/2 Python | Untouched |
| Win95 TLS | Still not claimed |

## Z-gate disposition

| ID | Disposition |
|---|---|
| Z0 zero-arg path | **Coded** (offline); live double-click smoke open |
| Z1 self-heal | **Pass** offline |
| Z2 6-digit PIN TTL | **Coded** |
| Z3 no cleartext long-term PSK | **Coded** (wrap/GRANT); live MitM review open |
| Z4 operators = chair after pair | **Coded** offline |
| Z5 lobby + JOIN after pair | **Coded**; default channel `#airc-moot` |
| Z6 ancient OS honesty | **Pass** (docs) |
| Z7 no secrets in git | **Pass** |
| Z8 offline tests | **Pass** |

## Nits / required follow-ups

1. **NC-ZC1 (blocker for zero-config UAT):** Live smoke: `--chair` on IONOS + zero-arg/`--pin` on walrus (or second nick on IONOS); sealed exec hostname; park log under docs/.
2. **NC-ZC2 (nit):** Confirm rolling `mode3-thin` release assets are 0.2.0 after CI.
3. **NC-ZC3 (nit):** Default lobby `#airc-moot` vs existing `#cm-bob-oscar` ops - document operator must align channel via sibling ini for Club Madeira field kit.

## Non-claims

- Win95 TLS
- Zero-config human UAT (until NC-ZC1)
- Replacement of `--key` air-gap path

## Sign-off

Bob - 2026-09-19 Europe/London - tip 2b1d743 - PASS-with-nits (live PIN smoke still open)
