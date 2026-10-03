<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/bobiverse.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Bobiverse (MODE2 moot on `#bobiverse`)

Fleet machines do **not** SMB-peek each other. Flamingo and MarchHare sit on bobnet copper; ionos is a VPS; DEV1 is the customer Azure box. Status rides a private Ergo on ionos (`irc.ntsa.uk:6697` TLS), not Libera. See `docs/bobiverse-ionos-ircd.md`.

Live shop-channel spec: `docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md` (issue #124) and `agentic_irc` issue #46.

## Channels

| | |
|---|---|
| Fleet | `#bobiverse` — Bob ACTION (`/me`) + working-on. MODE2 `free`. No POINT firehose. |
| Shop | `#flamingo` `#marchhare` `#ionos` `#ce-priority-dev1` (`#dev1` same channel) |
| Moot id | `b0b1be15e0000001` |
| Human talk | Short English PRIVMSG on real field change or one-shot long-running warning |
| Tray pull | `!bobiverse` ~every 120s from `bob-*` nicks; chair whispers `BOB DIGEST v1 i/n` JSON (full card) or legacy `BOB TRAY v1 …` kv lines |

Nicks (one builder Bob per machine):

| Machine id | Nick | Shop | Worker nick |
|---|---|---|---|
| flamingo | `bob-flamingo` | `#flamingo` | `w-fl-<pid>` |
| marchhare | `bob-marchhare` | `#marchhare` | `w-mh-<pid>` |
| ionos | `bob-ionos` | `#ionos` | `w-io-<pid>` |
| ce-priority-dev1 | `bob-dev1` | `#ce-priority-dev1` | `w-d1-<pid>` |

`bob-<id>` JOINs fleet + shop. Workers JOIN shop only. Key is `<id>:<pid>`.
Home on each box: `~\.agentic-irc-bobiverse`.
Worker home: `~\.agentic-irc-bobiverse\workers\<id>\<pid>`.

Machines persist in the digest as `I am online` / `I am offline`.
Disconnected workers are **deleted**. Bob drop closes that shop and deletes its workers.

`!report` is gone. Do not send it.

## Shop channels (`#<machine>`)

Each fleet box has a **shop** room `#<machine-id>` (`#flamingo`, `#marchhare`, `#ionos`, `#ce-priority-dev1`; `#dev1` is the same room as `#ce-priority-dev1`). `bob-*` builders JOIN `#bobiverse` **and** the local shop (`Get-BobIrcBuilderChannels` in `Watch-Bobiverse` / `Install-BobIrc`). Git/MRB workers never JOIN `#bobiverse`; they appear on the shop only as `w-<short>-<pid>` (`w-io-<pid>` on ionos, `w-fl-<pid>` on flamingo, etc.) via `Start-BobWorkerIrcAgent` → `agentic_irc` `start_worker_irc_agent.py`. No `!report` write path on IRC; digest updates use write-only `reportUrl` POST (below).

### Shop GIT backup (`!BORED` / `!TASK`)

Jeeves is the only nick that says `GIT` on `#bobiverse`. `bob-*` does not auto-claim those lines. When a `w-*` ear has been idle for more than 2 minutes, `Watch-Bobiverse` appends `PRIVMSG #<shop> :!BORED` to **that worker's** `outbox.txt` (not the builder outbox, not the chair outbox). Jeeves returns only the top not-yet-accepted row as `!TASK {repo} {task} {#id}` and marks it accepted in that step. The worker does not say `!ACCEPT`. It runs `Start-BobBuild` and posts `working_on` as `{agent} {model} {task} {repo}{#id}` to the digest webhook, then clears `working_on` when the job leaves inbox/running.

Not-yet-accepted rows are `git_unaccepted.items` on `https://irc.ntsa.uk/bob/v1/report` (`repo`, `task` `PR`|`MRB`, `id` `#n`, `seq`). This repo reads that document and does not write it. Do not merge until agentic_irc #197 follow-up uses the same object and the same `!TASK` accept step. Skill `bob-git-accept`.

After this lands on `main`, recycle **Watch-Bobiverse** on each box so the poller loads the shop tick. Recycle Jeeves only with the agentic_irc chair-queue change.

## Status on disk

`Write-BobIrcStatus` (Watch loop, ~30s) refreshes `~\.agentic-irc-bobiverse\bob-peers\<id>.json` with weekly bars, jobs, model/kind/repo/sha, and `lastSeen`. It does **not** append a `MOOT v1 POINT … BOB v1` line every tick (that was the Halloy firehose). When model, kind, repo, sha, hung/responding, or running/queued counts change, one conversational English line goes to the channel via `outbox.txt`.
Historical park (2026-09-20 quieter-talk intake, DM-centric `!bobiverse` later superseded by #74 / digest): `docs/feature-request-bobiverse-quiet-talk-2026-09-20.md` / issue #36.


On the same delta gate (not `lastSeen`-only), it may **POST** ionos `reportUrl` from `config/bobiverse.json` (`op=merge`, header `X-Bob-Secret` from `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret` — never git). The digest **chair** is nick **Jeeves** (`chairNick` in `config/bobiverse.json`). Watch does not start the chair.

## Jeeves (starts with the IRC server)

Jeeves is a second agent on ionos. His IRC `--home` is `~\.agentic-irc-jeeves`. `BOB_DIGEST_HOME` must be `~\.agentic-irc-bobiverse`, the directory `bobcallback` uses for `chair-outbox.txt` (`POST /bob/v1/git`). `fleet_digest_home()` follows that env. Without it, Jeeves drains his own home and GIT lines sit on the digest home. Do not pass the bob-ionos home as `--home` (QUIT/JOIN storm). Do not pass `--hello` or `--announce-key`.

**Canonical install (FR #330):** [SimonBarnett/gh-Jeeves](https://github.com/SimonBarnett/gh-Jeeves) `tools/Install-BobJeeves.ps1` — Windows service **`BobJeeves`**, `python -m jeeves`, token-less G1 gate. Prefer that over this repo’s legacy NSSM + `agentic_irc` wrapper.

**Legacy (this repo):** Service **`BobJeeves`** (Automatic, NSSM, depends on `BobIrcd`). Install: `tools/Install-BobJeeves.ps1 -AllowLegacyAgenticIrc` or `tools/Install-BobChair.ps1`. Boot starts `BobIrcd`, then `BobJeeves`. `Restart-Service BobIrcd` stops Jeeves and does not start him again:

```powershell
Restart-Service BobIrcd
Start-Service BobJeeves
```

Legacy command: `python -u scripts/irc_agent.py --host irc.ntsa.uk --port 6697 --nick Jeeves --channel #bobiverse --home <jeevesHome> --chair` with `AGENTIC_IRC_PASSWORD` from `~\.grok\ergo\connect.password` (never git) and `BOB_DIGEST_HOME` set to the digest home.

Tray peers for **other** machines: `Watch-Bobiverse` sends `!bobiverse` about every **120 seconds**, then ingests chair **`BOB DIGEST v1`** JSON whispers (chunked when needed) from `irc.log` into `bob-peers\` plus `cursor-pools.json` cache. Legacy **`BOB TRAY v1`** kv lines still work. Protocol: `agentic_irc` `!bobiverse` digest + issue #142 / `docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`.

Example tray line (machine-readable, not for channel spam):

```
BOB TRAY v1 id=ionos weekly=4 running=1 queued=0 repo=SimonBarnett/agentic_build kind=worker model=Cursor Models lastSeen=2026-09-21T00:00:00Z jobs=SimonBarnett/agentic_build:running
```

`BOB v1` POINT trailing text remains supported for transcript ingest (`Import-BobIrcPeerTranscript`) but is not the primary Watch publish path.

The tray paints **one weekly bar per registered `nicks` machine** from `bob-peers\`. Ghost IRC ids (`marchhare-bugets`, raw nicks) are dropped. `reach=irc-fallback` for those four seats. Repo stamps never publish `?` when a job is known.

## Install (each build box)

Python 3.12+ plus `pip install -r C:\ai\agentic_irc\requirements.txt`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Install-BobIrc.ps1 -MachineId flamingo -Chair
# other boxes: omit -Chair (JOIN)
```

`Watch-Bobiverse` keeps `irc_agent.py` on `#bobiverse` and `#<id>`.
MRB/build skills load `bob-shop-worker` and attach `w-<short>-<pid>`.

Ergo `PASS` is `~\.grok\ergo\connect.password`. Callback secret is
`~\.grok\bob\report.secret`. Do not commit either.

Do not open IRC from CI.

## Repo pair (`Start-BobRepoPair`)

`bob-{machine}` keeps two persistent shop workers (dev + MRB) per assigned
repo via `Start-BobRepoPair` / skill `bob-repo-pair` (issue #175). Workers
JOIN `#<machine>`; `Watch-Bobiverse` applies shop channel descriptions
(`Sync-BobShopChannelRepoDescriptions` ? SHOPDESC/TOPIC on the IRC outbox).
See `docs/feature-request-bob-two-persistent-workers-2026-09-22.md`.
