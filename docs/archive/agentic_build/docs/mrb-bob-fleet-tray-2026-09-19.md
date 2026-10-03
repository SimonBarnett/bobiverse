<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb-bob-fleet-tray-2026-09-19.md, last changed 2026-09-19. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Hostile MRB ?????" Bob Fleet system tray watcher (2026-09-19)

**Repo:** SimonBarnett/agentic_build  
**Surface:** `tools/Watch-BobTray.ps1`, `src/Public/Get-BobTrayHover.ps1`, `tools/Get-BobBoxUsage.ps1 -Hover`  
**HEAD reviewed:** `b1e856b` (Tray: FA robot icon, context remaining bar, jobs show machine)  
**Evidence:** live hover on MarchHare 2026-09-19 ~19:28 BST; operator screenshots (robot + dark card; Grok CLI weekly limit 9%); ionos Mode-3 job `9f96bc0e` running on `SimonBarnett/agentic_irc` while MarchHare tray idle.

## Verdict

**FAIL** ?????" not ready for human UAT as a *fleet* monitor.

The robot icon and dark card ship. The product claim in the UI ("Bob fleet" / "No fleet jobs running") does **not** match the data model. Context remaining is session-window math when `usage.json` exists; when it does not, the UI still draws a near-empty bar that operators read as "almost out" and confuse with Grok CLI **Weekly limit left**.

## Evidence

### E1 ?????" MarchHare live `Get-BobTrayHover` (this box)

```json
{
  "short": "SG idle",
  "body": "SG  context remaining  --\nno fleet jobs running",
  "remaining_pct": null,
  "remaining_kind": "context",
  "job_count": 0,
  "queued": 0,
  "jobs": [],
  "tier": "SG"
}
```

`Get-BobMachines` on MarchHare lists only `marchhare` / `marchhare-bugtest`. No ionos row. `Get-BobBuilds -Lane running` is empty locally.

### E2 ?????" Operator fact

Jobs **are** running on ionos (`agentic_irc` Mode 3 / related). Operator on MarchHare sees tray title **Bob fleet** and body **No fleet jobs running**. That is a false negative for any reasonable reading of "fleet".

### E3 ?????" Quota vs context

Grok CLI footer on a session: **Weekly limit left: 9%**. Tray card labels the bar **Context remaining**. Code path `Get-SessionContextRemaining` uses `usage.json` `(inputTokens - cachedReadTokens)` vs `models_cache` context_window (default 500000). It never reads weekly quota. Operators still equate the empty-looking bar with the 9% weekly figure. When `remaining_pct` is null, the painted bar must not look like ~0% remaining.

### E4 ?????" Code citations (failing behaviour)

- `Get-BobTrayHover`: only `Get-BobBuilds -Lane running` on **this** BobBridge store; still emits `no fleet jobs running`.
- `Watch-BobTray.ps1` `Update-Hover`: title always `Bob fleet`; empty jobs ?????' literal `No fleet jobs running`; bar caption `Context remaining` even when `$script:remainingPct` is null.
- Low-context pulse: fires when `remainingPct -lt 10` ?????" correct *if* metric is real; dangerous if null is coerced or bar mis-drawn.

## Non-conformances (ordered fixes)

### NC-01 (blocker) ?????" "Fleet" is local-only

**Fail:** UI claims fleet-wide visibility; data is per-machine BobBridge lanes only.

**Required:**
1. Rename idle copy to honesty: e.g. `No jobs on this machine` (not "fleet"), **or**
2. Implement true multi-machine hover: aggregate running jobs from every registered legion host the operator can see (ionos + marchhare + ???????), with machine column already present on job lines.
3. Title: `Bob fleet` only if (2); else `Bob (marchhare)` / `Bob (<machineId>)` matching the host.

Prefer (2) if the bridge already has cross-host records; if not, add a read-only peek of peer machine job stores / health endpoints documented in `docs/`. Do not invent remote APIs ?????" use existing BobBridge artefacts.

### NC-02 (blocker) ?????" Null context must not look depleted

**Fail:** With `remaining_pct: null`, card still shows a near-empty/red-looking bar; operators read "~0% left" and mix it with weekly 9%.

**Required:**
1. When remaining is unknown: bar **indeterminate or fully muted/hidden**, caption `Context remaining  ?????"` / `n/a` (match hover body `--`).
2. Never fill 0% unless computed remaining is actually 0 from `usage.json`.
3. Unit/script test: hover with no running jobs ?????' `remaining_pct` null ?????' tray paint path does not set fill width as empty-depleted.

### NC-03 (major) ?????" Surface weekly quota separately or not at all

**Fail:** Product copy and operator mental model collide (CONTEXT bar vs CLI weekly limit).

**Required:**
1. Keep context = session window only (current formula OK when `usage.json` exists).
2. Add optional second line **Weekly limit** only if CLI/settings expose a real field ?????" **do not invent**. If unavailable, document in hover skill: tray does not show weekly %; read CLI footer.
3. Update `.grok/skills/bob-fleet-tray/SKILL.md` and `box-usage` so agents never claim weekly from the context bar.

### NC-04 (major) ?????" Red badge semantics

**Fail:** Red badge present while idle + null context; unclear if stall alert vs context pulse.

**Required:**
1. Document badge sources: stall `ACTION_REQUIRED` vs context &lt;10% vs watcher down.
2. Do not pulse context when `remaining_pct` is null.
3. Prefer distinct badge colour or tooltip line: `alert: watcher|stall|context`.

### NC-05 (nit) ?????" Duplicate / stale job lines

If multiple lane records share one live `grok.exe`, collapse or show `jobId8` so three identical `ionos ??????? agentic_irc ??????? running` lines are diagnosable. Include `id8` in the visible tray line (hover body already has it; WinForms card currently drops it).

## Pass bar (next MRB)

- Operator on MarchHare can see ionos running jobs **or** UI never says "fleet" when it cannot.
- Null context ?????  depleted bar; screenshot/test proof.
- Skills state context vs weekly clearly.
- Badge/pulse never treats unknown as &lt;10%.
- Offline Test-Pack or focused tray tests cover NC-02 at minimum.

## Non-goals this ticket

- Redesigning FA robot artwork.
- Stopping in-flight ionos Mode-3 build.
- Inventing weekly-limit APIs the CLI does not expose.

## Hand-off

Build agent on **ionos**: implement NC-01???????NC-04 in priority order; commit + push `agentic_build`; leave Mode-3 `agentic_irc` job alone. Bob re-MRBs after push.