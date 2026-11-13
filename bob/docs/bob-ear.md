# Bob ear (fleet box)

Service **ircBob** -> `Start-Bob.ps1` -> **`scripts\bob-ear.exe`** (FR #1481, self-contained frozen `irc_agent`) or, on repo/dev trees without the exe, `python -u irc_agent.py`. Nick **`Bob-{MachineId}`**.
Companion: TipForm systray (`scripts\Start-BobTray.ps1` -> `tools\Start-BobFleetTray.ps1`).

Build/pack: `scripts\Build-BobEar.ps1` (PyInstaller) -> staged by `Pack-BobiverseRelease` into the bob MSI. Safe swap: `scripts\Install-BobEarExe.ps1` (keeps `bob-ear.exe.bak`, restores on smoke failure).

## Channels and homes

- JOIN `#bobiverse` + `#wonderland` + `#{MachineId}` (identical `Start-Bob` `--channel #bobiverse,#wonderland,#<machine>` on every box â€” Ionos host, MarchHare, Flamingo, â€¦; FR #3834)
- **DIGEST_ID_FOLD (harvest #2280 / PR #2279):** digest aliases fold to the real shop id â€” `ionos` -> `win-mpre8vi4u6u`, `dev1` -> `ce-priority-dev1`. Helpers (`inbound_transcript.channel_list_for_machine` / `canonical_machine_id`) must never emit `#ionos` or `#dev1` as the shop channel.
- After Jeeves `!register`: expect **+o** on shop, **+h** on `#bobiverse`, **+o** on `#wonderland` (FR #3834)
- Home: `<ai root>\bob\home` when ObjectName is LocalSystem; else often `~\.bobiverse`
- **`--home` isolation (FR #2350):** an explicit scratch `--home` (UAT under `%TEMP%`, â€¦) does **not** merge `~\.agentic-irc-bobiverse`. Fleet basenames `home` / `.bobiverse` still one-time migrate. Opt-in: `BOB_MIGRATE_LEGACY=1`. Opt-out: `BOB_HOME_NO_MIGRATE=1`.
- Agents: nick `{machine}-{pid}`, JOIN **shop only**

## Listen (inbound transcript) â€” FR #2174

Every running ear always appends scrubbed inbound PRIVMSG lines to:

```text
<bob home>\inbound-transcript.log
```

Each line is `UTC-timestamp channel nick text` (secrets redacted). The file rotates by size (`inbound-transcript.log.1` â€¦). This is **always on** â€” it does not need `BOB_IRC_DEBUG`. Raw wire dump (`irc.log`) remains opt-in via `BOB_IRC_DEBUG=1`.

Workers still only inject lines **FROM Jeeves** addressed to that seat (`bob_worker.accept_for_agent`); other PRIVMSG stay in the transcript for Shell/operators.

## Secrets

| Secret | Path / env |
|--------|------------|
| Ergo PASS | `<ai root>\bob\config\ergo.password` or `~\.grok\ergo\connect.password` |
| NickServ SASL | `<ai root>\bob\home\nickserv.password` -> `BOB_IRC_SASL_USER=bob-{machine}` |
| Service logon | `config\service.password` / `BOBIVERSE_SERVICE_PASSWORD` -> DPAPI `service.cred` |
| Digest POST | none (no secret; the digest accepts machine ids on the roster Jeeves publishes). **FR #6141 / #6145:** ircBob ear owns fuel merge POSTs (`publish_local_peer_fuel`); fingerprint deltas (remaining / OpenCode pcent / Copilot `overage_fetched_at` / `grok_account`) POST within `BOB_EAR_DIGEST_FUEL_DELTA_S` (default 5s, `DIGEST_FUEL_MAX_LAG_S`). Unchanged fingerprints wait for heartbeat (`BOB_EAR_DIGEST_FUEL_S`, default 30s). Watch-BobTray gathers peer JSON for paint only. **FR #6144 / #6188:** ear publish forwards an explicit peer `cursor_known` as a JSON boolean (omit when absent/null so legacy peers keep chair merge); when false the chair clears Cursor label/pcent/pools and does not peer-refill them. Sand resets use `sand_period_end` (not xAI `period_end`). **FR #6146:** when local OpenCode fuel is known, merge pcent includes `opencode-free` / `opencode-go` (omit when unknown; never invent 0). Helper reads use a short timeout + TTL cache so the 5s fuel tick cannot stall the outbox loop. |

Do **not** mint a fresh GUID for an already-registered NickServ account.

## Digest fuel publish (FR #6141..#6150)

Canonical digest: `GET https://bob.ntsa.uk/bob/v1/report`. The **ircBob ear** owns fuel merge POSTs (`publish_local_peer_fuel`); TipForm/Status paint only.

| Surface | Notes |
|--------|--------|
| OpenCode | `pcent.opencode-free` / `pcent.opencode-go` when local fuel known; omit unknown; never invent 0 |
| Copilot | TipForm/Status account-wide Copilot pool line; treat stale fetched_at as not current |
| Logos | `bob/tray/assets/fuel-logos/` (cursor, xai, opencode, copilot) + text fallback; see LICENSE.md |
| cursor_known | false clears Cursor label/pcent/pools; Sand uses `sand_period_end` |

Park drafts: `bob/docs/fr/digest-ear-publish/` (Refs, not Closes, for impl FRs). Vision: `bob/docs/vision-digest-ear-publish.md`.

## Public airc console roster (FR #5204 / FR #5947)

`GET https://bob.ntsa.uk/bob/v1/report` includes `airc_consoles` (flat nick list) plus `airc_console_details` (`[{nick, machine, channel}]`) and per-machine `console_nicks`. Chair NAMES on **every** channel Jeeves sits in (registered shops and customer channels) record live `*_console` nicks; PART/QUIT clears them. No NickServ, no secrets. Priority Agent airc picker can verify presence without IRC credentials.

## Outbox (send) â€” identical on every machine

UTF-8 **no BOM**. Append one complete line per send to `<bob home>\outbox.txt`. Only lines starting with `PRIVMSG ` are sent raw (same interface on Ionos / MarchHare / Flamingo):

```text
PRIVMSG <target> :<text>
PRIVMSG #<machine> :<shop line>
PRIVMSG #bobiverse :!help
PRIVMSG {machine}_console :<short-cmd>
```

Offset is tracked in `outbox.txt.pos`; up to 8 lines drain per tick. If `<ai root>\bob\home` is LocalSystem-ACL only, interactive users cannot write the outbox â€” use a talk-seat / worker run home for agent replies.

Raw shop-op verbs (bob-* ear, own `#{machine}` only; `shop_ops.raw_op_line`): `KICK`, `NAMES`, and `MODE +/-o|v|h <nick>` (FR #4069 adds half-op `+h`/`-h` alongside op/voice).

## Keepalive / half-open links (FR #4980)

After Ergo or a middlebox drops the session, TCP can stay `ESTABLISHED` while the
ear receives nothing. Talk-seat liveness does not cover `Bob-*` ears. The ear:

1. Sets a recv timeout (`BOB_IRC_RECV_TIMEOUT_S`, default 30s).
2. After `BOB_IRC_IDLE_PING_S` (default 60s) with no server traffic, sends a
   client `PING`.
3. If still no traffic for `BOB_IRC_IDLE_DEAD_S` (default 120s) after that PING,
   logs `INFO idle-dead (no PONG/traffic); reconnecting` and reconnects
   in-process (same as airc keepalive).

Workaround until this tip is deployed: `Restart-Service ircBob`.

## Absent / stale ear recovery

| State | Action |
|-------|--------|
| No `ircBob` / service Stopped | `Install-Bob.ps1` (or MSI) then `Start-Service ircBob` |
| Leftover `irc_listen.py` only (Flamingo-style) | Retire it; install/start `ircBob` ear above |
| Running but no `inbound-transcript.log` | `Restart-BobEar.ps1` after this FR is deployed |
| Running, socket ESTABLISHED, no transcript / deaf shop | FR #4980 keepalive; else `Restart-BobEar.ps1` |
| Missing `outbox.txt` | Ear recreates home on start; ensure service ObjectName/home path |

## Tray / recycle

- Product Sync/ff runs on **ircBob Start-Bob** only â€” TipForm Start never updates the tree.
- TipForm menu **Restart** -> `Restart-BobTrayWatcher` -> `Start-BobFleetTray -ForceNew` (restarts `ircBob` via `Restart-BobTrayService`, then relaunches TipForm in the interactive session so Sync/ff runs on ear start).
- Ear-only: Desktop / Start Menu **Restart ircBob** / `scripts\Restart-BobEar.ps1` (announce -> `Restart-Service ircBob`).
- **FR #2943 / VISION S3:** departure PRIVMSG + `depart-request.txt` go to the **service** ear home (`<InstallRoot>\home`, via `Get-BobiverseEarServiceHome`) â€” the path LocalSystem `Start-Bob` drains â€” not `%USERPROFILE%\.bobiverse` (orphan undrained outbox).
- Quiet MSI: `Start-BobTrayInteractive.ps1` registers ONLOGON `/IT` task `BobiverseTray` (no session-0 TipForm).
- `!recycle` / `!recycle {machine}`: announce -> restart tray + `ircBob`.
- **FR #6389:** if Jeeves routed `RECYCLE v1 <machine>` (or FR #197 shop route) but this ear did not restart, grep `logs\stdout.log` for `INFO recycle wire dropped reason=`. Reasons include `chair_mismatch`, `machine_mismatch`, `not_fleet_bob`, `chair_missing`, `is_chair`, `no_local_machine`, `not_recycle_wire`. Chair nick compare is case-insensitive. Success: `recycle announcing restart` then `recycle wire accepted`.
- **FR #5059** `!recycleseat <nick> [machine]`: authorised ops (+o/+h like `!register`), bob-* ear, Jeeves or owner queue a stop+verify+start for a named worker seat. The elevated tray consumes `run\recycleseat\req-*.json`; if stop fails or the PID is still alive, no new seat is started and the failure is reported to intake.
  **FR #5890:** the ear replies `NACK recycleseat: busy <nick>` with a reason when that seat has current digest work or was ACKed for recycle within the last 900 seconds. Per-seat `run\recycleseat\ack-<nick>.json` timestamps survive tray consumption and ear restarts; other seats are unaffected. Unreadable work evidence or ACK timestamps also NACK rather than queueing a destructive recycle. Commands naming another machine remain silent and are logged only in the ear's debug log. No flamingo ear hotpatch until Jeeves-side FR #5889 is merged and Simon authorises it.

## Standalone UAT / connect progress (FR #2351)

- `BOB_IRC_DEBUG=1` creates `<home>\irc.log` as soon as the Client starts (`debug-open`), then logs `session start` / `tcp-ok` / `tls-ok` (or `tls-fail`) before any IRC line arrives.
- TCP and TLS each use a 20s timeout so a hung handshake fails loudly instead of sitting silent after `prior-clean`.
- `--once` connects, JOINs, then exits (`INFO once: session complete`) â€” smoke/UAT friendly; omit `--once` for a long-running ear.
- `prior_irc` also matches frozen `bob-ear.exe` priors (same nick/home) and keeps PyInstaller onefile ancestors so the live child is not orphaned.
- Related: scratch `--home` must not merge `~\.agentic-irc-bobiverse` (FR #2350).

## Verify

```powershell
Get-Service ircBob
Get-Content <ai root>\bob\home\inbound-transcript.log -Tail 40 -ErrorAction SilentlyContinue
Get-Content <ai root>\bob\home\irc.log -Tail 40 -ErrorAction SilentlyContinue  # only when BOB_IRC_DEBUG=1
# Expect: SASL user=bob-<machine>, joined #bobiverse,#wonderland,#<machine> as Bob-<machine> (FR #3834)
# Expect: inbound-transcript.log lines like: 2026-10-04T12:00:00Z #marchhare Jeeves â€¦
# Scratch UAT: $env:BOB_IRC_DEBUG=1; bob-ear.exe --nick ear-test --home $tmp --channel #x --host irc.ntsa.uk --once
# Expect irc.log contains debug-open + tcp-ok + tls-ok; process exits after JOIN
```

## Related

- Skill: `.grok/skills/bobiverse-bob/SKILL.md`
- Post-install: `docs/post-install.md`
- Digest curls: `docs/webhooks.md` (hosted on jeeves)

## Grok account label on digest (FR #6143 / FR-003)

The fleet ear publishes `machines.<id>.grok_account` --- the signed-in xAI/Grok account label (email, or `first_name last_name` when email is absent). This is not `bob-<machine>` and is not `cursor_pools[].account`.

**Source (profile only):** resolve auth path in order `BOB_GROK_AUTH_PATH`, nonempty `GROK_AUTH_PATH`, `$GROK_HOME/auth.json`, then `~/.grok/auth.json`. Read only `email` / `first_name` / `last_name` from each non-`xai::api_key` entry. Never read or POST `key`, `refresh_token`, or other credentials. If the file is missing, has no profile, or has more than one distinct label, publish null (GET shows n/a). If the file is unreadable (I/O/JSON error), skip the POST so a transient failure does not clear a good label.

**Wire:** ear-owned scalar `grok_account` (kept out of peer fill / `_MERGE_PEER_FIELDS`). Label-only `op=merge` POST via `publish_grok_account_label` on the outbox tick (same cadence as digest fuel). Logs `grok account publish ok|failed` without the label or path.

**LocalSystem / service account:** if ircBob runs as a different Windows user than the interactive Grok login, set NSSM `BOB_GROK_AUTH_PATH` to that user's `auth.json` (never put the file contents in env).

**FR #6270 xAI weekly under LocalSystem:** the ear must not publish weekly from the system profile. Prefer `BOB_WEEKLY_LOG` (explicit unified.jsonl) or `BOB_GROK_WEEKLY_USER_HOME` (interactive user home). A live LocalSystem process may also resolve the console user's `Users\<name>\.grok\logs\unified.jsonl` (usage log only; never auth.json / credentials). When acquisition fails (including system-profile-skipped / no auth), FR #6274 keeps last-good remaining with true fetched_at, fresh=false, and an explicit error (do not blank a knowable value; revisits the older blank-on-skip behaviour). Diag fields: `home_role`, `acquisition`, `xai_weekly_fetched_at`, `xai_weekly_source`. Offline pins: `bob/tests/test_fr6270_ear_weekly_admin_profile.py`, `common/tests/test_fr6270_xai_weekly_interactive_profile.py`. Live provider page + digest screenshot remains Slab.

**FR #6995 SystemDrive pathlib root:** when auto-resolving `Users\<name>` under LocalSystem, build the path from a rooted `%SystemDrive%` (`C:\`, not bare `C:`). `Path("C:") / "Users" / name` is drive-relative on Windows and made every post-MSI ear report `system-profile-skipped` / `fresh=false` even when the interactive profile existed. Offline pin: `common/tests/test_fr6995_systemdrive_interactive_home.py`.

**FR #6282 handler isolation (reopen):** every inbound reader hook (NOTICE/chanserv-sync, PRIVMSG, JOIN/PART/QUIT, oper numerics, chair_wire, register-presence, SASL) goes through `_call_handler` / `_log_dispatch_error` so one AttributeError/TypeError logs a full redacted traceback (`irc-handler-error hook=...`) and leaves the session connected. `run_forever` logs the same for `session end`. Post-join ChanServ REGISTER and cursor-fuel refresh are wrapped. Startup `assert_ear_dispatch_contracts` covers gitclaim shop helpers and unregister_cmd ChanServ parse helpers. `gitclaim` stays frozen-embed only. Offline pins: `bob/tests/test_fr6282_gitclaim_handler_isolation.py`, `bob/tests/test_fr6282_dispatch_isolation_reopen.py`. Live MarchHare stay-joined remains Slab.

**FR #6274 live weekly fetch:** each ear fuel cycle calls the Grok CLI billing endpoint GET https://cli-chat-proxy.grok.com/v1/billing?format=credits using the interactive profile auth.json session key in-memory only (never copied, printed, or moved; optional BOB_GROK_AUTH_PATH). Source stamp: cli-chat-proxy:/v1/billing?format=credits with fetched_at at fetch time. Passive unified.jsonl is never posted as a fresh reading. On provider/auth failure keep last-good remaining with its true fetched_at, fresh=false, and an explicit error / age (do not blank a knowable value). Timeout: BOB_XAI_WEEKLY_FETCH_TIMEOUT_S (default 8).  Diag distinguishes auth-file-unreadable (ACL/PermissionError) from auth-key-missing (readable JSON with no session key/access_token). Layout: Grok CLI issuer::client_id map; entry.key (or access_token); skip xai::api_key slots; prefer non-expired expires_at. Do not grant or re-grant ACLs on auth.json (agent.exe resets them ~every 5 min); LocalSystem reads via SeBackupPrivilege + FILE_FLAG_BACKUP_SEMANTICS instead (never copy the file). FR #6279: weekly meter ``account`` / digest ``grok_account`` after a live fetch come from the *selected* auth entry only (same entry as the bearer); an unlabeled selected entry stays unattributed rather than borrowing a sibling profile label. FR #6274 ACL bypass: LocalSystem reads auth.json via SeBackupPrivilege + CreateFile FILE_FLAG_BACKUP_SEMANTICS (in memory only; never copies or changes ACLs); Grok agent.exe Admin-only resets are survived; failures still report auth-file-unreadable with win32 code. Offline pin: common/tests/test_fr6274_backup_semantics_auth.py. Offline pins: common/tests/test_fr6274_auth_layout_unreadable.py, common/tests/test_fr6274_live_xai_weekly_fetch.py, common/tests/test_mrb6277_fr6274_auth_bad_json.py. Live MarchHare agree-with-grok.com remains Slab.

**FR #6314 expired Grok sign-in:** billing HTTP 401/403 maps to meter/diag error ``grok-login-expired`` (distinct from ``provider-http-N`` / network / parse / 5xx). Last-good remaining + ``fetched_at`` stay, ``fresh=false``. Tray expands the class to ``Grok login expired: run Grok on <machine> to sign in again``. Ear never refreshes, rewrites, or copies auth.json and never logs tokens; one read per fuel interval; hub passes ``error`` through. Next successful read clears the error without a restart. Offline pins: ``common/tests/test_fr6314_grok_login_expired.py``, ``bob/tests/test_fr6314_tray_grok_login_expired.py``. Live MarchHare expired-then-re-sign-in proof remains Slab.


**Rejected sources:** `settings_cache.json` (no identity), `bob-seats.json` (configured attribution), ACP auth/info (not used here).

