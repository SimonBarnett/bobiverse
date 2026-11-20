# Bob ear (fleet box)

Service **ircBob** -> `Start-Bob.ps1` -> **`scripts\bob-ear.exe`** (FR #1481, self-contained frozen `irc_agent`; FR #7233 always this file when present — mtime vs `bobreport.py` is not used; start log includes sha256 / launcher_sha256 (Select-BobEarLaunch.ps1; FR #7390) / ear-component source (scripts\provenance.txt next to the exe; FR #7300 — never install-root MANIFEST) / VERSION. Python only when the exe is missing or `BOB_EAR_PYTHON=1`) or, on repo/dev trees without the exe, `python -u irc_agent.py`. Nick **`Bob-{MachineId}`**.
Companion: TipForm systray (`scripts\Start-BobTray.ps1` -> `tools\Start-BobFleetTray.ps1`).

Build/pack: `scripts\Build-BobEar.ps1` (PyInstaller) -> staged by `Pack-BobiverseRelease` into the bob MSI. Safe swap: `scripts\Install-BobEarExe.ps1` (keeps `bob-ear.exe.bak`, restores on smoke failure; optional -ProvenancePath installs CI provenance.txt beside the exe for source=; **FR #7390 / #7394:** when the CI artifact also ships `Start-Bob.ps1` / `Select-BobEarLaunch.ps1` / `Bobiverse-Common.ps1`, copies them into `scripts\` and checks their SHA-256 against the manifest).

**FR #7179 / #7202 CI (`build-bob-ear.yml`):** GitHub Actions on `windows-latest` compiles `bob-ear.exe` via `bob/scripts/Build-BobEar.ps1` on `push` to `main` and on `pull_request` whenever ear sources change. Path filters are the frozen `irc_agent` import graph under `common/scripts/` plus Build-BobEar pins (workflow, `Build-BobEar.ps1`, `Install-BobEarExe.ps1`, `deploy-pool-monitor-manifest.txt`, `bob/tests/ear_ci_source_paths.py` / `test_fr7179_*` / `test_fr7202_*` / `test_fr6254_*`), plus `workflow_dispatch`. A new frozen import that is missing from the YAML fails `test_fr7202_ear_ci_frozen_imports.py`. The job uploads artifact `bob-ear` with the exe, `bob-ear.exe.sha256`, **FR #7390 / #7394** `Start-Bob.ps1` + `Select-BobEarLaunch.ps1` + `Bobiverse-Common.ps1` (and their `.sha256` sidecars), `provenance.txt` / `manifest.txt` (`source_commit` / `workflow_commit` = the built tip SHA, exe SHA256, `start_bob_ps1_sha256` / `select_bob_ear_launch_ps1_sha256` / `bobiverse_common_ps1_sha256`, size, build time), and a copy of `deploy-pool-monitor-manifest.txt`. No hard behavior pin --- CI builds the checked-out commit (same shape as `build-bob-worker.yml` / `build-bob-tray.yml`). Not a release, MSI, or fleet install.

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
| Copilot | TipForm/Status account-wide Copilot pool line; treat stale fetched_at as not current. **FR #7255 / #7289 / #7377 / #7382:** Jeeves (walrus) fetches Copilot and OpenCode Go on a dedicated fixed-rate 60s timer (independent of chair busy and of outbox drain) into digest `fleet_pools`. Machine ears do not GET those providers (xAI stays per ear). Cursor token is CredMan `Bobiverse/CursorAccess` on walrus. |
| Logos | `bob/tray/assets/fuel-logos/` (cursor, xai, opencode, copilot) + text fallback; see LICENSE.md |
| cursor_known | false clears Cursor label/pcent/pools; Sand uses `sand_period_end` |
| python (FR #7020 / #7022 / #7035) | `publish_local_peer_fuel` reads `<home>/run/python-status.json` and posts `python=missing` or a source tag only (never a path body). On a later successful SYSTEM resolve the ear calls `note_python_resolved` (rewrite tag or unlink) so digest never keeps stale `python=missing`. |

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

**FR #8120:** every IRC SSL read and write shares one lock (OpenSSL is not concurrent-safe). Non-registration sends are dropped until `001`; the outbox thread starts only after registration. TLS/handshake failures reconnect on a short backoff (seconds). A reserved/ghosted `Bob-*` nick uses `GHOST`/`RELEASE` then retry with `BOB_IRC_NICK_RESERVED_BACKOFF_S` (default 30, max 120) instead of a fixed 300s sit-out. Connect failures log `INFO connect-fail cause=...` without secrets.

**FR #7839:** the outbox tick keeps running after an exception (including the old `OSError` return that stopped fuel while the reader stayed up). A fuel POST runs on its own thread; if that thread is still in flight after 2 minutes the ear logs and reports `digest-fuel-stall` and later ticks continue. On `GET /bob/v1/report`, a machine whose `lastSeen` is older than 2 minutes is offline, and an `xai_weekly.fetched_at` older than 2 minutes keeps the last percent and period end with `fresh: false`. That stale row files `ear-publish-stale` (deduped) only for this ear, and only when the reported age is still inside the six-hour pool window. A remote machine, or a timestamp older than that window, is still marked stale and is not filed. An in-window `lastSeen` stall is still filed when `fetched_at` is already past the window. The filed message omits the changing age (FR #7892).

**FR #7896:** a digest lock whose holder thread has exited is reclaimed inside the live ear. Disk-full during the locked section is reported as `digest-publish-enospc` and the lock is released. If the outbox loop has stopped while IRC is up, the session idle tick starts it again and files one `digest-publish-loop-dead` report. That tick runs for bob-* ears, not only talk-seat liveness.

**FR #8103:** a clean `finally` release unlinks `digest.lock` and clears holder metadata so the next publish cycle does not log a false `lock-broken reason=dead-thread`. True orphans still break with a rate-limited log that names the lock, thread, acquire site, and cause; `/health` exposes `lock_break_count` and `lock_hold_exception_count`. An exception raised while the lock is held is logged once and the lock is released by `finally` (no break).

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
- **FR #5059** `!recycleseat <nick> [machine]`: authorised ops (+o/+h like `!register`), bob-* ear, Jeeves or owner queue a stop+verify+start for a named worker seat. The elevated tray consumes `run\recycleseat\req-*.json`; if stop fails or the PID is still alive, no new seat is started. Stop failures and launch errors still report to intake; a still-alive refuse only logs `reason=still-alive` (FR #7688) and must not open a tray RuntimeError crash issue for a live worker.
  **FR #8321:** recycle restores the clicked kind **and model** from `run\clicked-seats.txt`; a paid V4 Pro seat comes back paid, a free Flash seat comes back free, and a saved model that is paused/capped refuses to start instead of silently switching. The post-install restart uses the same path.
  **FR #8403:** when several `!recycleseat` reqs are pending the tray stops every seat first and launches the replacements afterwards (serialize stop+start), so the 2-seat cap cannot leave a stopped seat with `launch-failed` while a later Ensure path fills the gap anonymously. A restore launch is `-Restore` (net-zero) and bypasses the cap. A launch that still returns no pid is named in `res-*.json` (`seats-off` / `cap` / `worker-exe-missing`), never a bare `launch-failed`. `kind-unknown` (no click record) stays a planned refuse (FR #7835).
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

**FR #7907 Cursor CLI account:** the ear publishes `cursor_account` (email, or literal `none`), `cursor_account_user` (interactive Windows account leaf) and `cursor_account_source` (`api_key` or cleared). Source file is `<interactive home>\.cursor\cli-config.json` (`authInfo.email` only; `BOB_CURSOR_CLI_CONFIG_PATH` for tests). The interactive home is the same resolver as the Grok weekly profile. A legacy tray key prompt writes `cursor-key-override.json` (source, pid, time; never the key) under the interactive user's `%LOCALAPPDATA%\Bobiverse\tray\run`; the ear reports `api_key` only while that pid is alive. The ear never reads tokens. Logs say `cursor account publish ok|failed` without the label or path.

**LocalSystem / service account:** if ircBob runs as a different Windows user than the interactive Grok login, set NSSM `BOB_GROK_AUTH_PATH` to that user's `auth.json` (never put the file contents in env).

**FR #7176 xAI weekly as SYSTEM (no system-profile-skipped):** when ircBob runs as LocalSystem, the ear must fetch xAI usage itself. Skipping because of SYSTEM is not allowed. Auth path order under LocalSystem: `BOB_GROK_AUTH_PATH` / `GROK_AUTH_PATH`, then the **machine store** interactive `Users\<seat>\.grok\auth.json` (same file seats use after FR #7183; FR #7235 — re-read every fetch, never a frozen copy under `<InstallRoot>\home\.grok`), then stamped `<InstallRoot>\run\grok-auth-path.txt` (path only), then service-home last resort. Live LocalSystem with no resolvable auth reports `auth-unresolved` (never `system-profile-skipped`). `grok-login-expired` keeps last-good stale and records the auth **path** (never contents). No secrets in logs, IRC, issues, or the digest. Offline pins: `common/tests/test_fr7176_localsystem_xai_service_auth.py`, `common/tests/test_fr7235_system_ear_machine_grok_auth.py`. Live MarchHare two-interval digest+systray proof remains Slab.

**FR #6270 xAI weekly under LocalSystem:** the ear must not publish weekly from the system profile. Prefer `BOB_WEEKLY_LOG` (explicit unified.jsonl) or `BOB_GROK_WEEKLY_USER_HOME` (interactive user home). A live LocalSystem process may also resolve the console user's `Users\<name>\.grok\logs\unified.jsonl` (usage log only; never auth.json / credentials). When acquisition fails (including system-profile-skipped / no auth), FR #6274 keeps last-good remaining with true fetched_at, fresh=false, and an explicit error (do not blank a knowable value; revisits the older blank-on-skip behaviour). Diag fields: `home_role`, `acquisition`, `xai_weekly_fetched_at`, `xai_weekly_source`. Offline pins: `bob/tests/test_fr6270_ear_weekly_admin_profile.py`, `common/tests/test_fr6270_xai_weekly_interactive_profile.py`. Live provider page + digest screenshot remains Slab.

**FR #6995 SystemDrive pathlib root:** when auto-resolving `Users\<name>` under LocalSystem, build the path from a rooted `%SystemDrive%` (`C:\`, not bare `C:`). `Path("C:") / "Users" / name` is drive-relative on Windows and made every post-MSI ear report `system-profile-skipped` / `fresh=false` even when the interactive profile existed. Offline pin: `common/tests/test_fr6995_systemdrive_interactive_home.py`.

**FR #7006 nobody logged on:** CIM `Win32_ComputerSystem.UserName` and explorer owner are empty in session 0 with no console logon. Fall back to HKLM `LogonUI\\LastLoggedOnUser` (SAM name only) then `<InstallRoot>\\run\\interactive-user-home.txt` (path written after a successful resolve; never a key). NSSM `BOB_GROK_WEEKLY_USER_HOME` / `BOB_GROK_AUTH_PATH` still win. Offline pin: `common/tests/test_fr7006_nologin_interactive_home.py`.

**FR #7177 OpenCode Go as SYSTEM (no missing_key / empty-as-fresh):** under LocalSystem the ear resolves the Go key from `BOB_OPENCODE_GO_API_KEY`, `<InstallRoot>\config\opencode-keys\*.apikey` / `opencode-go.apikey` (root via `BOB_INSTALL_ROOT` or frozen `scripts\bob-ear.exe` parent), then seat `auth.json` via SeBackupPrivilege. Install re-applies a prior NSSM `BOB_OPENCODE_GO_API_KEY` across service recreate (never echoed). A recognised but empty usage body is kind `empty` (failure). Unknown / no-key windows carry null `fetched_at` so an advancing timestamp always means a real measurement. Offline pin: `common/tests/test_fr7177_localsystem_opencode_go.py`. Live MarchHare two-interval digest+systray proof remains Slab.

**FR #6996 OpenCode under LocalSystem after MSI:** the ear (session 0) owns OpenCode pool publish. It must not skip because SYSTEM PATH lacks WinGet Links. Resolve `opencode.exe` from `BOB_OPENCODE_EXE`, then the interactive seat user's `AppData\Local\Microsoft\WinGet\Links\opencode.exe` (MarchHare evidence). Go zen key: bob `config\opencode-keys` / `opencode-go.apikey` first, else seat `%USERPROFILE%\.local\share\opencode\auth.json` via SeBackupPrivilege (never log the key). No exe and no auth file => digest window error `not installed`; exe present without a Go key => `no key set`. Tray paints those errors instead of a single n/a. Offline pin: `common/tests/test_fr6996_service_opencode_winget.py`.

**FR #6282 handler isolation (reopen):** every inbound reader hook (NOTICE/chanserv-sync, PRIVMSG, JOIN/PART/QUIT, oper numerics, chair_wire, register-presence, SASL) goes through `_call_handler` / `_log_dispatch_error` so one AttributeError/TypeError logs a full redacted traceback (`irc-handler-error hook=...`) and leaves the session connected. `run_forever` logs the same for `session end`. Post-join ChanServ REGISTER and cursor-fuel refresh are wrapped. Startup `assert_ear_dispatch_contracts` covers gitclaim shop helpers and unregister_cmd ChanServ parse helpers. `gitclaim` stays frozen-embed only. Offline pins: `bob/tests/test_fr6282_gitclaim_handler_isolation.py`, `bob/tests/test_fr6282_dispatch_isolation_reopen.py`. Live MarchHare stay-joined remains Slab.

**FR #8049 transient 503:** one provider 502/503/504 within the 120s stale window keeps `xai_weekly.fresh=true` and last-good `%` / period end; the tray must not paint the status. Past the window: last `%` with `[stale]`. Acquisition stamps `error_source` to `cli-chat-proxy:/v1/billing?format=credits`. **FR #6274 live weekly fetch:** each ear fuel cycle calls the Grok CLI billing endpoint GET https://cli-chat-proxy.grok.com/v1/billing?format=credits using the interactive profile auth.json session key in-memory only (never copied, printed, or moved; optional BOB_GROK_AUTH_PATH). Source stamp: cli-chat-proxy:/v1/billing?format=credits with fetched_at at fetch time. Passive unified.jsonl is never posted as a fresh reading. On provider/auth failure keep last-good remaining with its true fetched_at, fresh=false, and an explicit error / age (do not blank a knowable value) **when the cached reading is for the same grok_account**. **FR #7400:** a cached xAI weekly is bound to the account it was fetched for; if auth.json switches account, discard that remaining/used/reset and publish unknown for the new account until a successful fetch (do not paint the old % under the new name). Offline pin: `common/tests/test_fr7400_xai_cache_bound_to_account.py`. Timeout: BOB_XAI_WEEKLY_FETCH_TIMEOUT_S (default 8).  Diag distinguishes auth-file-unreadable (ACL/PermissionError) from auth-key-missing (readable JSON with no session key/access_token). Layout: Grok CLI issuer::client_id map; entry.key (or access_token); skip xai::api_key slots; prefer non-expired expires_at. Do not grant or re-grant ACLs on auth.json (agent.exe resets them ~every 5 min); LocalSystem reads via SeBackupPrivilege + FILE_FLAG_BACKUP_SEMANTICS instead (never copy the file). FR #6279: weekly meter ``account`` / digest ``grok_account`` after a live fetch come from the *selected* auth entry only (same entry as the bearer); an unlabeled selected entry stays unattributed rather than borrowing a sibling profile label. FR #6274 ACL bypass: LocalSystem reads auth.json via SeBackupPrivilege + CreateFile FILE_FLAG_BACKUP_SEMANTICS (in memory only; never copies or changes ACLs); Grok agent.exe Admin-only resets are survived; failures still report auth-file-unreadable with win32 code. Offline pin: common/tests/test_fr6274_backup_semantics_auth.py. Offline pins: common/tests/test_fr6274_auth_layout_unreadable.py, common/tests/test_fr6274_live_xai_weekly_fetch.py, common/tests/test_mrb6277_fr6274_auth_bad_json.py. Live MarchHare agree-with-grok.com remains Slab.

**FR #7399 unused Premium / omitted percent:** when `/v1/billing?format=credits` returns a usable weekly period but omits `creditUsagePercent` (protobuf-style JSON for 0% used), the ear treats used as 0 / remaining as 100 and publishes a fresh reading. Reject only when the body is unusable (no period); reject diagnostics log config field names, never secret values.

**FR #6314 / FR #7345 / FR #7464 expired Grok sign-in:** when the access token is expired or under a 10-minute lead and a ``refresh_token`` is present, the ear refreshes via ``https://auth.x.ai/oauth2/token`` (Grok CLI public client) and rewrites ``auth.json`` atomically in the CLI format so machines with no seat stay fresh past the ~6h access lifetime. ``grok-login-expired`` / tray ``sign in once on <machine>`` only when that refresh is rejected (or no refresh material remains). Billing HTTP 401/403 after a failed/absent refresh still maps to ``grok-login-expired`` (distinct from ``provider-http-N`` / network / parse / 5xx). Peer stamps ``xai_auth`` ``expired`` or ``ok`` (self-heals on the next good read). Last-good remaining + ``fetched_at`` stay, ``fresh=false``. Never logs tokens; one resolve per fuel interval of the **machine** store (FR #7235); hub passes ``error`` through and diag may name the auth **path**. Offline pins: ``common/tests/test_fr6314_grok_login_expired.py``, ``common/tests/test_fr7464_xai_access_token_refresh.py``, ``bob/tests/test_fr6314_tray_grok_login_expired.py``, ``bob/tests/test_fr7345_grok_never_blocks_auth.py``. Live MarchHare expired-then-re-sign-in proof remains Slab.


**FR #7251 / #7298 / #7365 / #7471 ear pool fetch 60s:** `EAR_POOL_FETCH_S` (60). SYSTEM ear live-fetches **xAI weekly** every 60 seconds (Copilot / OpenCode / Cursor are Jeeves fleet). Each attempt logs `xai_attempt=` / `xai_weekly_error=` (no secrets). **FR #7365:** `xai_attempt=ok` only when the reading was applied to peer/digest; otherwise `not-fresh` / `not-known` / `cached-reading` / the acquisition error. A successful live apply stamps `fetched_at` to the fetch clock (never leave a cached provider timestamp), writes the peer file, and POSTs within that publish. Failure keeps last-good remaining, stamps `last_attempt_at` plus `error` (grok-login-expired adds `error_action` "sign in once on the machine"), and marks stale after 2 minutes. FR #7471: never stretch past 60s (429/Retry-After is logged as the row error, never applied as silent backoff); auth.json mtime change forces an immediate re-check. Offline pins: `common/tests/test_fr7251_ear_pool_fetch.py`, `common/tests/test_fr7298_ear_xai_refetch.py`, `common/tests/test_fr7365_xai_fetched_at_advances.py`.

**Rejected sources:** `settings_cache.json` (no identity), `bob-seats.json` (configured attribution), ACP auth/info (not used here).

