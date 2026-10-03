<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-two-persistent-workers-2026-09-22.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: bob-{machine} two persistent workers per repo

**Parked:** 2026-09-22 by flamingo-24108 from Simon Query.  
**Repo:** SimonBarnett/agentic_build (extends current fleet; do not break v1 job loop).

## Proposed flow (Simon check this logic)

```mermaid
flowchart TB
  IN["FR or functional spec for a new repo\nusually turns up"]
  IN --> PARK["bob-machine parks issue + /docs"]
  PARK --> CHAIR["bob-machine is the grok chair\ninstalled on every box\nbobiverse skills"]
  TIX["Bob also checks outstanding tickets\nevery 2 hours during business hours\nand assigns them"]
  TIX --> ASSIGN
  CHAIR --> DESC["#channel description = assigned repo\nchange when the repo changes"]
  CHAIR --> PAIR["Bob MUST start agents with\nIRC + build skills\nBob directs them to JOIN IRC"]
  CHAIR --> ASSIGN["Bob orders and assigns MRB vs dev\ncan assign any idle over 20s agent on bobiverse"]
  CHAIR --> IDLEMRB["If Bob not responding:\nidle worker MRBs the open PR"]
  CHAIR --> RT["Bob decides which to invoke:\nlocal agent vs agent.com"]
  RT --> PAIR
  CHAIR --> MON["Bob monitors processes in flight\nrestart if they stop responding"]
  CHAIR --> PING15["Every 15 min Bob pings own shop\ncheck connections / online\nintervene if workers stalled"]
  CHAIR --> USE["Each bob webhooks identity +\nreal pools only: grok chat / high cost / low cost\n+ local xAI grok weekly\nNOT Club Madeira or Smart Catalogue pools"]
  USE --> MIN["Each pool: remaining % + next period start\n0 is 0 not n/a; n/a only if unavailable\nMUST webhook; lesser of Cursor variance"]
  CHAIR --> JEEVES["Every time Bob calls !bobiverse:\nif Cursor or local xAI changed, POST webhook"]
  CHAIR --> OPS["bob-machine is ops in own shop channel\nJeeves is ops in #bobiverse"]
  MIN --> TRAY["Control systray shows proper Cursor meters\ngrok chat / high cost / low cost\nremaining % + next period; 0 is 0"]

  subgraph PAIRBOX["One repo, two workers — persist until idle a few minutes"]
    WA["Worker A: implement next PR\ndev model: LESS\nelse local xAI if Cursor tokens out"]
    WB["Worker B: MRB that PR\nMRB model: MEDIUM\nelse local xAI if Cursor tokens out\nnew FRs + tests\nmerge duplicate issues\nclose finished issues\nmerge PR if PASS-nits"]
  end

  PAIR --> WA
  PAIR --> WB
  ASSIGN --> WA
  ASSIGN --> WB
  MON -.-> PAIRBOX
  WA -->|"A does the work itself\nopen PR; never invoke another agent"| WB
  WB -->|"B MRBs itself; never invoke another agent\nFAIL: do not merge"| FIX["A FIXes its own PR\nthen B re-MRBs"]
  FIX --> WA
  WB -->|"PASS-nits: MRB worker merges"| NEXT{"More PRs / FRs?"}
  NEXT -->|yes| SWAP["Implementer moves to next PR\nother worker MRBs"]
  SWAP --> WA
  NEXT -->|both idle a few minutes| HARV["Bob reminds workers to harvest skills"]
  HARV --> STOP["Bob may terminate the pair"]

  WA --> POST["Workers MUST POST working_on to webhook\nNO channel PRIVMSG — webhook only"]
  WB --> POST
  POST --> DIG["Digest updates"]
  DIG --> SAY["Bob reads digest\ndev complete / MRB complete\nreports to #bobiverse"]
  NEXT -->|PASS-nits and ready| UAT["Bob chair only: UAT skill\nUAT model: MORE\nworkers never stamp UAT"]
```

## Ask (LOCKED)

Change how Bob works:

1. **`bob-{machine}` is the grok agent** on that box.
2. He is **installed on all machines** and is given the skills to **join the bobiverse**.
3. Input is either a **feature request** or a **functional spec for a new repo**.
4. Bob **starts 2 workers** to handle the project (one repo) he is assigned.
5. Those agents **persist** until Bob no longer needs them.
6. Workers are **spawned by Bob** with **build + IRC** skills. They do **dev or MRB**.
7. **No self-review:** if one worker implemented a PR, the **other** must MRB; the implementer **moves to the next PR**.
8. Bob **does not terminate** workers until they have been **idle a few minutes**.
9. Workers **MUST** POST their current **working-on description to the webhook**.
10. That update **must appear on the digest** so we can see what everyone is working on.
11. **Bob refers to the digest** (MRB complete / dev complete / similar states) **to report to the bobiverse**.
12. The **repo name** a `#channel` is working on **is the channel description**. **Change it when the repo changes.**
13. **Bob** (chair only) **uses the new UAT skill** (`bob-design-uat` / design-uat) **to approve UAT**. Workers do not stamp UAT.
14. **Workers do their own work.** They **do not invoke another agent** (no nested Start-BobBuild / handoff spawn). The pair *is* the two workers.
15. **Bob monitors** worker processes **during flight** and **restarts** them if they stop responding.
16. **Bob orders and assigns** MRB vs dev tasks (chair assigns the role; worker executes it).
17. FRs **usually turn up**. Bob is also responsible for **checking outstanding tickets** and **assigning** them — **every 2 hours during business hours**.
18. **Workers dynamically switch model by role:** **dev = less**, **MRB = medium**, **UAT = more**. Cursor first; local xAI if tokens out. Never Other Models.
19. **MRB also:** merge **duplicate issues**, **close** issues that are done/superseded, and **merge PRs if PASS-nits**.
20. **Each bob** sends a **webhook to identify itself** and **how much local grok is left** on its account.
21. **Each bob** also reports the **Cursor values it sees for the whole account**. **Take the lesser of any variance.**
23. Usage pools are the **real Cursor/xAI meters**, not seat nicknames. There is **no Club Madeira pool** and **no Smart Catalogue pool** (those are xAI seat labels in `bob-seats.json`). Report:
    - **grok chat** (Sand)
    - **high cost models**
    - **low cost models** (cursor-models fuel)
    - **local xAI / Grok Build weekly** (per box seat)
    For each: **percent remaining** and **when the next period starts**. **0 shows 0, not n/a.** **n/a only when that pool is not available.** Every pool **MUST** be posted on the webhook.
24. **Workers use Cursor** unless **out of tokens**, then **their local xAI accounts**.
25. **Bob decides which to invoke:** `agent` (local) or `agent.com` (cloud).
26. **Every time Bob calls `!bobiverse`**, he **POSTs the webhook if anything changed** on **Cursor or local xAI** (change-only).
27. **`bob-{machine}` is ops in their own shop channel.** **Jeeves is ops in `#bobiverse`.**
28. **Update the control systray** to the **proper Cursor metrics** (grok chat / high cost / low cost — remaining % + next period; 0 is 0). Not seat-nickname pools.
29. Model pick is **dynamic per task kind** (dev/MRB/UAT → less/medium/more), not a single model for the pair.
30. **Bob MUST start agents with the IRC and build skills.**
31. **Bob must direct them to JOIN IRC.**
32. **Every 15 minutes** Bob **pings in his own shop** to check **connections / online**, and **intervenes if workers are stalled**.
33. **Bob can assign to any idle (>20 sec) agent on the bobiverse.**
34. **If Bob is not responding**, find an **idle worker to MRB your PR**.
35. **Bob must remind workers to harvest their skills before dismissing them.**
22. **Workers do not send to the channel.** They **report only through the webhook**.

## Gap vs current tree (`be8cb6f`)

| Today | Required |
|-------|----------|
| `Start-BobBuild` / `Start-BobBuildLoop` / `Start-BobMrbHandoff` enqueue one-shot cursor/grok jobs; Watch-BobJobs pulls the queue | `bob-{machine}` (grok) owns a repo and keeps **two** live workers |
| Workers are `w-<short>-<pid>` shop-only, or ephemeral cursor-agent PIDs | Persist until Bob idles them out |
| MRB is a **new** job (`-Kind mrb`), never the implementer | Same pair: implementer vs MRB seat; implementer proceeds to next PR |
| `post_working_on` exists on talk seats (`#102` / agentic_irc) | **Workers** must POST; digest must show it |
| Talk seats + Watch recycle `bob-*` | `bob-{machine}` stays the grok chair on every box with bobiverse skills |

Do not break: hostile MRB (not own PR), no UAT stamp by workers, no `!bobiverse` from builders, no Other Models.

## MUST NOT

- Implementer reviews or merges their own PR (except PASS-nits MRB worker merge, existing rule).
- Stamp ready for human UAT (Bob chair only).
- Commit secrets / `password=` / API key assignments.
- Second-open a duplicate FR if this issue is the home.

## UNKNOWN

| ID | Item |
|----|------|
| U1 | Exact idle timeout (Simon: "a few minutes") — default **5 min** unless he sets it. |
| U2 | Whether the two workers are grok.exe, cursor-agent, or mixed (dev Composer / MRB Cursor Grok as today). |
| U3 | How this replaces vs wraps `Start-BobBuildLoop` on the same SHA. |
| U4 | New-repo path vs existing `bob-spec-intake` create-repo. |
| U5 | Business-hours window (tz + start/end). Cadence LOCKED: every 2 hours. |
| U6 | Exact Cursor/xAI slugs for less / medium / more (dev / MRB / UAT). |

## Acceptance

| ID | Check |
|----|--------|
| A1 | Skill/docs: `bob-{machine}` = grok chair; two workers per assigned repo. |
| A2 | Bob MUST start workers with IRC + build skills and **direct them to JOIN IRC**. |
| A3 | Persist until Bob stops them after idle timeout (U1). |
| A4 | Implementer cannot MRB that PR; the other worker MRBs; implementer takes next PR. |
| A5 | Worker `working_on` POSTs to webhook; digest shows the description. |
| A6 | Bob reads digest states (dev complete / MRB complete / …) and reports them on #bobiverse. |
| A7 | Shop/channel **description** = current repo name; update when the assigned repo changes. |
| A8 | Bob chair approves UAT via the new UAT skill; workers never stamp UAT. |
| A9 | Workers implement/MRB/FIX themselves; they do not invoke another agent. |
| A10 | Bob monitors in-flight processes and restarts if deaf. Shop ping every 15 min; intervene if stalled. |
| A11 | Bob assigns MRB vs dev; can assign any bobiverse agent idle > 20s. |
| A12 | Bob checks outstanding tickets every 2 hours during business hours and assigns them (FRs also arrive). |
| A13 | Dynamic models: dev=less, MRB=medium, UAT=more (Cursor then local xAI). |
| A14 | MRB merges duplicate issues, closes finished/superseded issues, merges PASS-nits PRs. |
| A15 | Each bob webhooks identity + local grok remaining. |
| A16 | Each bob reports account-wide Cursor values; fleet uses the lesser if they differ. |
| A17 | Workers do not PRIVMSG shop/fleet channels; status is webhook-only. |
| A18 | Webhook usage = real pools (grok chat / high / low / local grok weekly). No Madeira/Catalogue pool names. |
| A19 | Each pool: remaining % + next period start; 0 is 0; n/a only if unavailable; MUST report. |
| A20 | Workers use Cursor until tokens are out, then local xAI. |
| A21 | Bob chooses local `agent` vs `agent.com` for each invoke. |
| A22 | On each Bob `!bobiverse`, webhook if Cursor or local xAI usage changed. |
| A23 | `bob-{machine}` is ops on `#{machine}`; Jeeves is ops on `#bobiverse`. |
| A24 | Control systray paints proper Cursor meters (not Madeira/Catalogue pool names). |
| A25 | BT0/docs validator or pack test covers A1–A24 enough to MRB. |
