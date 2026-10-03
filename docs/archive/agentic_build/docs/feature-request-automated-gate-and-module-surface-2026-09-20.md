<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-automated-gate-and-module-surface-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: an automated gate — run Test-Pack on push, and assert the BobBridge surface `tools/*.ps1` actually calls

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Raised by:** MRB worker (Cursor Models) while reviewing 3280605 for issue #13
**UAT + hostile MRB owner:** Bob
**Related:** `tools/Test-Pack.ps1`, `src/BobBridge.psd1`, `tools/Start-BobMrbHandoff.ps1`, issues #9, #11, #12

## Gap vs current tree

Two holes that 3280605 made visible. Neither is covered by an existing issue or `/docs` markdown.

### 1. There is no automated gate

`.github/` contains exactly one file, `copilot-instructions.md`. There are no workflows.
`tools/Test-Pack.ps1` is the only gate in the repo and it runs only when a human types it.
Nothing runs on push, on PR, or on a schedule, so "23 pass / 0 fail" is a claim a reviewer
has to re-earn by hand on every SHA — and a red pack can sit on `main` unnoticed.

It is also not reproducible from a dirty checkout. Several cases (`BT0o bobiverse irc` and
the other `Get-Content $RepoRoot\tools\...` assertions) read the **working tree**, not the
commit. On the box that reviewed 3280605 the pack reported 1 fail against the dirty
checkout and 0 fail against a clean `git worktree` of the same SHA. A worker that trusts
the in-place run will report the wrong result for the commit it was asked to review.

### 2. Nothing checks that `tools/*.ps1` only calls exported BobBridge functions

`src/BobBridge.psd1` has an explicit `FunctionsToExport` list. Helpers defined in
`src/Private/*.ps1` are not in it. Scripts under `tools/` import the module and then call
functions by name, with no check that the name is on the public list — so a private helper
resolves fine while the author is testing inside the module and fails at runtime for
everyone else.

3280605 shipped exactly this bug: `tools/Start-BobMrbHandoff.ps1` calls `Get-ThisMachineId`,
which is defined in `src/Private/Invoke-BobFleet.ps1` and is not exported. The call is
wrapped in `catch { }`, so the failure is silent and the preflight it guards degrades to a
no-op. The full pack was green.

## Ask

1. A CI workflow (GitHub Actions, `windows-latest`) that runs `tools/Test-Pack.ps1` on push
   to `main` and on pull requests, and fails the check when any case fails. Offline only —
   no live `gh`, no live agent, no fleet share, no quota spend.
2. `Test-Pack.ps1` cases that read repository source must read the commit under test, not
   whatever is in the working tree, or the pack must state loudly at start that it is
   running against a dirty checkout and name the modified files.
3. A Test-Pack case that enumerates every BobBridge function name invoked by `tools/*.ps1`
   and fails when one of them is not in `FunctionsToExport`.
4. A lint pass for the module and tools: unapproved PowerShell verbs, empty `catch { }` on a
   code path that feeds a gate, and parameters accepted but never read. PSScriptAnalyzer is
   the obvious vehicle; whatever is chosen must run in the same CI check.

## Acceptance

1. A red `Test-Pack` blocks the check on a pull request; a green one passes it. Evidenced by
   a deliberately failing case, not by assertion.
2. The surface case fails today's tree (because of `Get-ThisMachineId`) and passes once the
   function is exported or the caller is changed.
3. The pack run in a dirty checkout either matches the clean-worktree result or says it is
   dirty and lists the files.
4. CI spends no Cursor, Grok Build, Grok Bot, or Copilot quota, and needs no GitHub token
   beyond the default workflow token.
5. No secrets in the repo, the workflow, or the job packets.

## Non-goals

- Changing any MRB verdict bar (`bob-hostile-mrb` owns those).
- Fleet `gh` provisioning and readiness reporting — that is issue #11.
- The MRB loop automation itself (per-SHA board, back-link) — that is issue #9.
- Replacing `Test-Pack.ps1` with a different test framework.
