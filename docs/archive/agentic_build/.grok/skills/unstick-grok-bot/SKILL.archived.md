<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/unstick-grok-bot/SKILL.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: unstick-grok-bot
description: >
  Diagnose and unstick a named Grok Bot (Bob, Haitch, Merc, …) that has stopped
  responding. Use when the user says agent not responding, stalled agent, hung
  Grok Bot, ping no reply, empty agent screen, Temporal PENDING, RecreateSandBox,
  InterruptGrokBotAgentRun, or /unstick-grok-bot. Fleet job queue / Watch-BobJobs
  is grok-build-fleet, not this skill.
---

# Unstick a named Grok Bot

The agent's turn runs in a **Temporal** harness (`workflowId` `grok-bot-turn-<agentId>`). Tool exec may be this Windows computer **or** a cloud sandbox (VNC = "agent's screen"). A wedged turn accepts new chats as `GROK_BOT_SEND_STATUS_PENDING` and never writes them to the transcript. The Grok Bot UI can show those bubbles anyway.

`$api = Join-Path $repo 'tools\GrokBotApi.py'` (`$repo` as in grok-build-fleet). `post` redacts token/url/credential fields.

## 1. Snapshot — do not send

```powershell
python $api list
python $api interrupt --agent <Name>
```

Roster `last` is the agent's last **assistant** line. User pings do not move it. WIP last line (`starting with`, `then commit`, `working on`, `about to`) plus stale `lastActivityAt` is a hung generation, not idle.

`interrupt` `hadActiveRun: true` means a turn is live. `hadActiveRun` omitted/false means idle. Interrupt **does not always end** a wedged turn. Do not queue more prompts while PENDING.

## 2. Transcript is source of truth

```powershell
python $api post --agent <Name> --method ListGrokBotTranscriptEntries
python $api post --agent <Name> --method GetGrokBotSendStatus --json '{"messageId":"<id>"}'
```

Newest `send-message` is the last committed assistant line. UI messages missing from the transcript are optimistic/PENDING. `GROK_BOT_SEND_STATUS_PENDING` = Temporal has the bytes, the turn has not ingested them. `ACCEPTED` + new `echoEntryId` = recovered.

## 3. Where it is wedged

```powershell
python $api post --method ListGrokBotUserComputers
python $api post --service aiserver.v1.SandBoxService --agent <Name> --method GetSandBoxRunState
```

- This box as `hello.label` = computer-use host. Restarting Grok Bot desktop reconnects that host; it does **not** cancel Temporal.
- `sand-session-marker.json` `aliveAtMs` is start time, not a heartbeat. Use a live `Grok Bot.exe` process (CIM `Name` matches `Grok Bot`).
- `GetSandBoxRunState` `SAND_BOX_RUN_STATE_RUNNING` + PENDING sends after interrupt = cloud box/turn wedged. Empty "agent's screen" is that pod's VNC.
- User `GROK_BOT_SEND_STATUS_ACCEPTED` (echo in transcript) with **no later assistant `send-message`** is the same wedge. Roster `last` stays on the previous assistant line.

`PollGrokBotUserComputerRequests` empty does not mean the turn is healthy.

**Sand weekly 100% (check before Recreate):**

```powershell
python $api post --service aiserver.v1.DashboardService --method GetSandUsageStatus
```

`usagePercent: 100` + silent `ACCEPTED_TEMPORAL` (no assistant `send-message`, no limit banner) is empty Grok Bot Sand, not a wedged pod. `hasAvailableUsage: true` / on-demand on does not prove generation. Also `ListGrokBotStripeLinkPaymentMethods`: `OUTCOME_NEEDS_AUTH` means on-demand cannot charge (box 503). Cursor billing **Open** invoices / unpaid-invoice banner is the same block. Reset: `nextResetTimestampUtc`. Owner skill: `cursor-sand-billing` (pay path) / `box-usage` (numbers). Do not RecreateSandBox for that. Human: pay Open invoices, finish Stripe Link.

## 4. Recreate the sandbox (when 3 says wedged)

Named bots on this Grok Bot desktop **share one cloud sandbox**. Recreate **once** (pass `--agent` so `agentId` is set). Do not Recreate per agent; a second Recreate starts another "Updating Grok Bot's Computer / Transferring your data" and UI sends sit on **Waiting to send**.

```powershell
python $api post --service aiserver.v1.SandBoxService --agent <Name> --method RecreateSandBox --json '{"preserveData":true,"force":true}'
python $api post --service aiserver.v1.SandBoxService --agent <Name> --method EnsureSandBox --json '{"wake":true}'
```

`--agent` is required. `started: true` is not done. Poll `EnsureSandBox` until `podId` **differs** from the pre-recreate id (can take 1-3 minutes; Ensure may time out mid-transfer). Then two samples ~30s apart on the **new** id, `runState` RUNNING, no transfer toast. Two stable samples of the **old** id mean recreate has not taken yet. Never print `execDaemon*`, `vncUrl`, `gatewayToken`, `networkToken`.

Do **not** `send` (API or UI) until the new `podId` is stable.

`Waiting to send` in the UI is PENDING (not in the transcript). Cancel it after the toast is gone.

Preferred ping is the **Grok Bot UI**, one line, after transfer. Interrupt until `hadActiveRun` is omitted first. Pre-unstick API bubbles may never get a `send-message`.

API PONG only after a UI ping has produced an assistant `send-message` (transcript, not roster `lastActivityAt` — that moves on user echoes). `GrokBotApi.py --wait` uses that transcript check.

```powershell
python $api interrupt --agent <Name>
python $api send --agent <Name> --text "Reply with exactly PONG and then stop. Do not use tools." --wait --timeout 90
```

Tell the human to send a **new** ping in the Grok Bot UI if the turn still has no assistant `send-message`.

If a **second idle agent** (not the stuck one) also `ACCEPTED_TEMPORAL` with no assistant `send-message`, and Sand is **not** 100%, this is a Temporal harness outage, not a single-agent wedge. Stronger probe: `CreateGrokBotTemporalAgent` a throwaway agent and PONG it.

If that new `grok-bot-turn-<newId>` also never `send-message`, stop RecreateSandBox. `isFork` still uses the same workflow id. `CreateGrokBotAgent` with `harness: box` (forum: box was live when temporal was deaf) may 503 Service Unavailable while temporal still ACCEPTED_TEMPORAL with no reply. Sandbox/desktop recycle will not start a generating turn. Wait for Cursor Grok Bot backend; do not stack more API PONGs. Do not delete the original bots.

## 5. Desktop process gone

Start `"C:\Program Files\Grok Bot\Grok Bot.exe"`. Wait until CIM shows `Grok Bot.exe` and `GrokBotApi.py health` `signedIn`. Then go back to step 1. Desktop restart alone is not the unstick.

## Do not

- Send follow-up work into a PENDING turn.
- Treat unread counts as agent stalls (those are human-unread).
- WinRM, Windows service, or SQL passwords.
- Dump sandbox URLs or tokens.
- Treat a blank/frozen Electron window as a Temporal hang — that is
  `setup-remote-grok-bot` (window-state 0x0 / no-GPU shortcut).
