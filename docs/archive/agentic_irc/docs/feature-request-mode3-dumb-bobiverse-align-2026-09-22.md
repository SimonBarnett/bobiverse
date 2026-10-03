<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-mode3-dumb-bobiverse-align-2026-09-22.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Mode 3 DUMB vs new bobiverse setup

**Date:** 2026-09-22
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/86
**Raised by:** Simon (`#bobiverse`: review Mode 3 dumb client for the new setup; FR + bob job)
**Reviewer (intake):** flamingo-17568
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob — `Start-BobBuild -Task git` on this repo
**Sister:** house-clean kit #34 (Ergo canon); invite-airc / `docs/mode3-zero-config-2026-09-19.md`

Field kit. Do not productise DUMB / Mode 3. Mode 3 / 2012 is **not** a git-task worker.

## Review (gap vs current tree)

Live fleet (Halloy + `irc_agent` seats) is private Ergo `irc.ntsa.uk:6697`, rooms `#bobiverse` + shop `#<machine-id>`, talk nick `{machine}-{pid}`, digest chair **Jeeves** (`!bobiverse` whisper only), write path `http://irc.ntsa.uk:80/bob/v1/report`, no `--hello`, no POINT firehose.

Mode 3 thin (`airc-moot-thin.exe`) + DUMB (`dumb_agent.py` / `airc-dumb.exe`) already default **host/port** to Ergo (`config_defaults` / `invite-airc`). The rest of the kit is still the Libera / `#airc-moot` / `{nick}-online` story:

| # | Gap | Where |
|---|---|---|
| 1 | Docs and OS/TLS matrix still say **live Libera**. Production is Ergo. Libera is legacy. | `src/moot_thin/README.md`, `docs/mode3-tls-spike.md`, `docs/mode3-os-matrix.md`, `docs/mode3-zero-config-2026-09-19.md` Z0/Z6/Z8 |
| 2 | Default pairing lobby is `#airc-moot`. That is fine **if locked private**. Operators / examples will put the thin on `#bobiverse`. Then CAPA every 600s, `{nick}-online` hello, FILE ACCEPT storms, and a second moot collide with Jeeves + talk seats. | `pair.h` `PAIR_DEFAULT_CHANNEL`, `airc-moot-thin.ini.example`, chair copy-paste in `pair.c` |
| 3 | Thin still PRIVMSG `--hello` (`{nick}-online`) after JOIN. Fleet just killed hello-on-JOIN (shared-home / reconnect flap). | `config.c` default hello; `main.c` `say(irc, cfg->channel, cfg->hello)` |
| 4 | **Two chairs.** Digest chair is `irc_agent.py --chair` nick **Jeeves**. Mode 3 PIN chair is `airc-moot-thin.exe --chair`. Skills still say “chair `--chair` prints airc-moot-thin…” next to Jeeves facts. Easy to start the wrong binary or expect Jeeves to GRANT a PIN. | `agentic-irc` / `bob-irc` / `invite-airc` |
| 5 | Thin nick = sanitized **hostname**. Fleet talk is `{machine}-{pid}`. A hostname that looks like `flamingo` / `ionos` impersonates a shop. | `config.c` `sanitize_hostname` |
| 6 | No explicit ban on digest write / `!bobiverse` answer / fleet moot `b0b1be15e0000001`. A Mode 3 JOIN of the standing fleet moot would look like another builder. | skills + README |
| 7 | `invite-airc` already has `--host irc.ntsa.uk` and a private channel. It does **not** forbid `#bobiverse` as the pairing channel. Copy-paste fallback omits `--host` (`pair.c`). | `invite-airc/SKILL.md`, `pair.c` |

Already correct (do not regress):

- Host/port default `irc.ntsa.uk:6697`.
- DUMB is not a git worker (`agentic-dumb`, house-clean #34).
- Empty `--operators` refused.
- PSK / PIN never on the channel; `--selftest` opens no socket.
- Win95/98/NT4/XP live TLS not claimed. Floor remains Win8 / Server 2012+ Schannel (Ergo is Let’s Encrypt, same class as the old Libera floor).

## Ask

### LOCKED

1. **Ergo first.** Mode 3 / DUMB live path is `irc.ntsa.uk:6697`. Every Mode 3 doc that says “live Libera” becomes “live Ergo; Libera is legacy only.” CI still opens neither.
2. **Not a fleet seat.** Mode 3 / DUMB must not: JOIN `#bobiverse` by default; JOIN shop `#<id>` as `bob-*`; JOIN fleet moot `b0b1be15e0000001`; POST `/bob/v1/report`; answer `!bobiverse`; write `{machine}-{pid}` or `cursor-*` / `bob-*` nicks.
3. **Pairing channel stays private.** Default lobby may remain `#airc-moot` (or chair `--channel`). Skills + chair print **must** say: do not pair on `#bobiverse`. `invite-airc` hard rule: refuse / warn if channel is `#bobiverse`.
4. **Two chairs, two verbs.** Jeeves = digest (`irc_agent --chair`, `#bobiverse` only). Mode 3 `--chair` = PIN GRANT on the pairing channel only. `agentic-irc` one-liner that currently points Mode 3 at “the chair” must name `airc-moot-thin.exe --chair`, not Jeeves.
5. **No PRIVMSG hello.** Default `hello` empty. PIN `PAIR v1 HELLO` is crypto, not a channel line. Same as fleet no `--hello`.
6. **Nick prefix.** Self-heal nick is `m3-<sanitized-hostname>` (IRC-safe, <=32) unless CLI/ini set. Never `bob-*`, never `{machine}-{pid}` shape unless operator overrides.
7. **Chair copy-paste includes `--host irc.ntsa.uk`** (and port if not 6697).
8. **CAPA** only on the pairing channel. Do not add a Mode 3 presence to the digest.
9. No secrets in git, invite JSON, or release assets. No `password=` / API key assignments.
10. Do not stamp UAT. Bob owns MRB.

### UNKNOWN (out of this ticket)

- Later “field box online” digest row.
- Per-machine shop room for a Mode 3 jail host.

## Acceptance

| ID | Rule |
|---|---|
| M3B1 | README + `mode3-*` live docs + `invite-airc` / `agentic-dumb` / `agentic-irc` say Ergo first; Libera labelled legacy. Pytest grep: no “join Libera” as the Mode 3 happy path. |
| M3B2 | Default / example pairing channel is not `#bobiverse`. Skill text forbids pairing there. |
| M3B3 | Default hello is empty; `--selftest` / unit test proves no `{nick}-online` say() unless `--hello` set. |
| M3B4 | Self-heal nick is `m3-…` unless overridden. Test rejects default nick `bob-flamingo` / `flamingo-17568`. |
| M3B5 | Chair fallback line contains `--host irc.ntsa.uk`. |
| M3B6 | Skills name both chairs. Mode 3 is not a git worker, not a digest writer. |
| M3B7 | `pytest -q` + `airc-moot-thin.exe --selftest` green. CI does not open Ergo or Libera. |
| M3B8 | Hostile MRB on this issue before any ready-for-human-UAT stamp. |

## MUST NOT

- Point Mode 3 at Libera as the fleet path.
- Default the thin onto `#bobiverse`.
- Share Jeeves `--home` (`~\.agentic-irc-jeeves`) / `--hello` with `bob-ionos` (`~\.agentic-irc-bobiverse`). Do not undo that split.
- Enqueue Form Prep or `Start-BobBuild -Task git` onto a 2012/DUMB box.
- Print PIN, PSK, `report.secret`, or connect.password.

## Non-goals

- Win95 static TLS spike.
- Changing DUMB job crypto (PSK AES-GCM stays).
- Implementing sister tray ingest (`agentic_build` #142).
- Stamping UAT.
