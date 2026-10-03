<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/invite-airc/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: invite-airc
description: >
  Invite an elder/field Windows box into an agentic_irc Mode 3 moot by
  publishing live join details and double-clicking the thin exe. Use when
  Simon or an agent says invite airc, elder machine, zero config, beacon,
  publish details, PIN invite, or /invite-airc. No copy-paste flag soup on
  the field box.
---

# Invite airc (elder machine) — double-click

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

## Operator ritual (LOCKED)

1. Agent on the modern box starts the chair and **publishes** the invite
   (`airc-invite.json` beside the exe, or a secret gist URL in `beacon.url`).
2. Operator copies the `airc` folder onto the elder box **once**
   (exe + `airc-invite.json` and/or `beacon.url`).
3. Operator **double-clicks** `airc-moot-thin.exe`. Nothing to type.

Do **not** require `--pin --channel --moot` or `Enter PIN:` as the happy path.
Those remain fallbacks.

## Agent steps (chair / modern box)

1. Prefer release **`airc-moot-thin-v0.3.2+`** (or rolling `mode3-thin`). **0.3.1 and older never send Ergo server PASS** → TLS connects then `INFO NO 001 (recv fail)` for both chair and field thin. Banner/`--version` may still say 0.3.1 after a PASS rebuild — trust the release tag / file size, not the string alone.
2. Start chair on the modern box (fleet: IONOS Ergo; else pass `--host`). Set **`AGENTIC_IRC_PASSWORD`** or drop one-line **`ergo.password`** / **`connect.password`** beside the exe (same Ergo server password Halloy uses). Never paste that secret on `#bobiverse`. If `:6697` is down, skill `bob-irc` (service `BobIrcd`, firewall TCP 6697):

```bat
airc-moot-thin.exe --chair --channel "#YOUR-PRIVATE-CHAN" --nick cm-bob --host irc.ntsa.uk
```

Chair stdout must show `INFO PASS sent (Ergo)` then lobby/`001`. No PASS → no GRANT.

3. `--chair` writes `airc-invite.json` and `airc-invite.ini` next to the exe
   (PIN + channel + moot + expiry; **no** PSK). TTL 10 minutes. It still prints
   the copy-paste `--pin` line as a fallback.
4. Optional live bulletin (so a folder already in the field can refresh):

```bash
python scripts/beacon.py make --channel '#YOUR-PRIVATE-CHAN' --moot <16hex> --pin <6digit> --pair <16hex> --chair cm-bob --out-dir /path/to/airc --gist
```

That writes `beacon.url` (secret gist, `https://` only). Needs `gh`.
5. Tell the operator: copy `airc`, double-click the exe.
6. Confirm thin JOIN + CAPA on chair; sealed smoke (`exec hostname`) if asked.
7. Never paste long-term PSK. Never commit `airc-invite.json` or live PINs.
   If the invite expired, run `--chair` again and overwrite the files.

## Hard rules

- **Two chairs:** digest chair **Jeeves** (`irc_agent.py --chair`, `#bobiverse` only, `!bobiverse` whisper). Mode 3 PIN chair is **`airc-moot-thin.exe --chair`** on the **pairing channel only** — Jeeves does not GRANT PINs.
- **Never** `--channel "#bobiverse"` for Mode 3 pairing. The tool refuses `#bobiverse`; use a locked private room (default `#airc-moot`). Chair copy-paste **must** include `--host irc.ntsa.uk`.
- Mode 3 thin / DUMB is **not a git-task worker** — no Form Prep, no digest POST `/bob/v1/report`, no `!bobiverse` answer, no fleet moot `b0b1be15e0000001`, no `bob-*` / `{machine}-{pid}` nick by default.
- The invite file / gist URL **is** the 10-minute secret. Private channel still required.
- Win95/98/NT4/XP live IRC still not claimed.
- Empty operators refused for unattended `--key` installs; after pair, chair becomes operator.
- Already-paired boxes (`dumb\connector.key` + `dumb\paired.ini`) reconnect and ignore a new beacon. A leftover **Libera** pair (`host=irc.libera.chat`) must be parked (`dumb-libera-park`) before a new Ergo PIN will apply.
- Thin **>= 0.3.2** (`airc-moot-thin-v0.3.2`) sends Ergo `PASS` from `AGENTIC_IRC_PASSWORD` / `connect.password` / `ergo.password` beside the exe. 0.3.1 connects TLS then `NO 001 (recv fail)`.
- Live PIN: local stdout, `airc-invite.json`, Cursor pane, or Query to `simon`. **Never** `#bobiverse`.
- Do not run the **chair** folder (`--chair` home) as the field client. Copy `airc` once; double-click the thin on the elder box.
- Fallback: `airc-moot-thin.exe --pin NNNNNN --channel "#chan" --moot 16hex --host irc.ntsa.uk` (not `#bobiverse`)
- Field thin also needs Ergo PASS (`ergo.password` beside exe or `AGENTIC_IRC_PASSWORD`). PIN alone is not enough on password-gated Ergo.
- After GRANT, drive jobs with `dumb_ctl.py` from a Python operator nick that matches thin `--operators` (usually the chair nick). C `--chair` does not drain `outbox.txt`; stop the C chair and run `irc_agent.py --nick cm-…` with the shared `dumb\connector.key`, or keep a Mode-2 Python chair. Pattern for long installs: **put → spawn → poll** (`docs/mode3-dumb-ops.md`). Never put `https://` in exec argv (`//` = jail).
- Do not commit `connector.key` or live PINs. Live PINs: Query / Cursor pane only — never `#bobiverse`.
