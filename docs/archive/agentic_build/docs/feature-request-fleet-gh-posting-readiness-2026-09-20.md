<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-fleet-gh-posting-readiness-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: fleet GitHub-posting readiness — provision and report `gh` on every git-task worker

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Raised by:** MRB worker (Cursor Models) while reviewing fb56d4a for issue #10
**UAT + hostile MRB owner:** Bob
**Related:** `tools/Start-BobMrbHandoff.ps1` (preflight landed fb56d4a), `.grok/skills/cursor-mrb-dev`, issue #9

## Gap vs current tree

fb56d4a added `Test-BobGhIssuePosting` to `tools/Start-BobMrbHandoff.ps1`: the handoff now
throws if `gh.exe` is missing, so an MRB can no longer be dispatched from a box that cannot
post. That is the right gate, but it only *refuses*. Nothing provisions or reports the
capability, so the loop loses machines with no remediation path:

1. **No provisioning.** `src/Public/Install-BobFleet.ps1` installs the module, skills and
   pull worker. It never installs GitHub CLI and never checks auth. `gh` appears in exactly
   three files (`tools/Start-BobMrb.ps1`, `tools/Start-BobMrbHandoff.ps1`,
   `tools/Start-BobCopilot.ps1`) and in `.grok/skills/cursor-mrb-dev` as manual prose
   ("`winget install GitHub.cli` ; `gh auth login`").
2. **No health signal.** `Get-BobHealth` reports machine up / jobs / scratch / fuel. It does
   not report "this box can open an issue on the product repo", so `Select-BobGitWorker`
   can still pick a machine that will dead-end an MRB, and the operator only learns at
   dispatch time (or, on the grok-build fallback, after the reasoning model has been spent
   on the remote box).
3. **No token contract.** The landed preflight accepts any non-empty `GH_TOKEN` /
   `GITHUB_TOKEN` without validating it, and no skill documents where that token is meant to
   come from on a fleet box or which scopes it needs. On this box the review reached GitHub
   only through a credential-manager token, which no skill names.

## Ask

1. `Install-BobFleet` installs / verifies GitHub CLI on the target machine (idempotent;
   winget when available, documented manual path otherwise) and records the result.
2. `Get-BobHealth` (and the capacity snapshot it feeds) exposes a posting-readiness field —
   `gh` present, authenticated, and `issues:write` on the product repo — so the picker and
   the tray can see it. Eligibility for `kind=mrb` git tasks should consider it.
3. A documented, non-interactive token contract for unattended workers: which env var, which
   scopes, where it lives on a fleet box, and how it is rotated. No `password=` or token
   assignments in git.
4. Validate rather than sniff: presence of `GH_TOKEN` is not proof of a live token. Probe it
   (`gh auth status` honours the env var, or a single cheap API read) before reporting ready.

## Acceptance

1. Off-DEV Test-Pack cases (Fake-Grok / fixture, no live `gh`, no live agent) for: readiness
   reported false when `gh` is absent, false when the token probe fails, true on a fixture
   that reports both, and a `kind=mrb` git task that never selects a not-ready machine.
2. `Install-BobFleet` on a machine without GitHub CLI leaves it either installed or reported
   as not-ready, never silently unchanged.
3. `Get-BobHealth` output carries the readiness field; the tray / `box-usage` card can show it.
4. `cursor-mrb-dev` and `grok-build-fleet` document the token contract and the remediation
   step, so a preflight failure names the fix.
5. No secrets in the repo, the job packets, or the prompts.

## Non-goals

- Changing the MRB verdict bars (that is `bob-hostile-mrb`).
- Replacing the fb56d4a preflight; this feeds it better information.
- Copilot provisioning (`start-bob-copilot` owns its own auth).
- Storing any token in git or in a job packet.
