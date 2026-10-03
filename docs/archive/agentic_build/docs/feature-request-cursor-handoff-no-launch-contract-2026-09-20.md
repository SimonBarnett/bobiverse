<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-cursor-handoff-no-launch-contract-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: explicit no-launch contract for `Start-BobCursor` (stop keying test safety off a grok env var)

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Raised by:** MRB worker (Cursor Models) while reviewing fb56d4a for issue #10
**UAT + hostile MRB owner:** Bob
**Related:** `tools/Start-BobCursor.ps1`, `src/Private/Invoke-BobFleet.ps1`, `tools/Test-Pack.ps1`, issue #9

## Gap vs current tree

fb56d4a added `BT0q kind mrb packet`, the first Test-Pack case that invokes
`tools/Start-BobCursor.ps1` for real. That script writes a handoff packet **and then spawns a
live `cursor-agent` via `Win32_Process.Create`**. The new case does not spend Cursor quota
only because of this line:

```powershell
if ($agent -and $Cwd -and -not ($env:BOB_GROK_EXE -match '(?i)Fake-Grok')) {
```

Test safety for a **Cursor** launch therefore depends on a **grok** environment variable
happening to point at `tools/Fake-Grok.ps1`, which `Import-Bridge` sets. The contract is
implicit and undocumented:

1. **No opt-out switch.** There is no `-NoLaunch` / `-WhatIf` / `BOB_NO_AGENT_LAUNCH` on
   `Start-BobCursor.ps1`. Any caller that wants the packet without the process must fake a
   grok exe path. A future test (or a human sanity-checking a packet) that forgets will start
   a real reasoning-model session against a fixture cwd and a fixture goal.
2. **Asymmetric fleet guard.** In `src/Private/Invoke-BobFleet.ps1` the `copilot` branch is
   guarded by `-not (Test-BobUsesFakeGrok)` before it hands off; the `cursor-models` branch
   has no such guard and relies entirely on the env sniff inside `Start-BobCursor.ps1`.
   fb56d4a edited that exact branch (to pass `-Kind`) without closing the asymmetry.
3. **Unvalidated kind from the packet.** The same branch now forwards
   `[string]$packet.kind` into a `[ValidateSet('mrb','build')]` parameter. A packet with any
   other `kind` turns a handoff into a caught exception and a `failed` job, where it used to
   be ignored. The packet field has no schema validation on the enqueue side.

Issue #9 asks that *new* loop tests avoid a live agent; it does not give the mechanism, and it
does not cover the existing fleet paths that can reach the launch.

## Ask

1. An explicit no-launch contract on `tools/Start-BobCursor.ps1`: a `-NoLaunch` switch (and/or
   honouring a single documented env var) that writes the packet, returns
   `started=$false` with a reason, and never calls `Win32_Process.Create`.
2. `tools/Test-Pack.ps1` uses that switch rather than depending on `BOB_GROK_EXE` naming.
   Keep the env sniff as a belt-and-braces backstop, but it must not be the only guard.
3. Symmetric guard in `src/Private/Invoke-BobFleet.ps1`: the `cursor-models` handoff respects
   the same fake/dry-run gate the `copilot` branch already respects.
4. Validate `kind` where the job is enqueued (and in `schemas/`), so a malformed packet is
   rejected at enqueue instead of failing the job at handoff.

## Acceptance

1. Off-DEV Test-Pack: `Start-BobCursor.ps1 -NoLaunch` writes a packet, reports not started with
   a reason, and spawns no process — asserted with a process count, not by inspecting output.
2. With a real `cursor-agent` present on the box, the full pack still starts no agent process.
3. A queued `fuel=cursor-models` git job processed by the fleet loop under Fake-Grok hands off
   without launching an agent.
4. A job packet with `kind=<not mrb|build>` is refused at enqueue with a named error, not
   surfaced as a `failed` job after dispatch.
5. No live GitHub, no live `%USERPROFILE%\.grok\bob-bridge`, no live agent in any new case.

## Non-goals

- Changing which model each `kind` resolves to (`config/default.json` owns that).
- Removing the `Fake-Grok` transport sniff used elsewhere in the bridge.
- The MRB loop driver itself (issue #9).
