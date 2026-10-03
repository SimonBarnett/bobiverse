<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/mrb.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# MRB (lightweight)

Hostile Material Review Board is a **GitHub issue** on the product repo,
linked to the **feature-request issue**, `docs/feature-request-*.md`, and
the **worker PR**.

Do **not** write `docs/mrb-*.pdf`. Git is the source of truth.

Transaction (no judgment): `.grok/skills/bob-build-loop`.

1. Worker opens a PR. Never push `main`. Never merge (**FR #343** - other seat MRBs).
2. Bob hands off MRB with `tools/Start-BobBuildLoop.ps1` (skill
   `bob-job-loop`) or a single `tools/Start-BobMrbHandoff.ps1` (Cursor Models
   while remaining > 0, else grok.exe). Never Other Models.
3. In a temporary worktree, use `gh pr checkout`, read intent **and the repo
   vision** (FR #351: `VISION.md` / brief / README purpose / CAST IRON), add NEW
   tests, run existing + new tests, and perform the hostile review **plus drift
   check**. Drift FAIL is like a test FAIL. Quote the vision lines used.
4. **PASS:** review README, skills, `docs/`, mermaid diagrams, and usage/help
   text for stale behavior. If anything is stale, open exactly ONE **separate**
   `docs/mrb-<n>` PR against `main` (never push onto the reviewed branch) and
   merge it with the original; if docs are fine, merge the original as before.
   Close the source issue/FR, then hand off to a separate UAT worker. Only Bob
   stamps UAT.
5. **FAIL:** open exactly ONE **separate** fix PR with the fix, then merge both
   the original PR and the fix PR. Do not open multiple fix PRs.
6. Worker posts `MRB FAIL|PASS-nits: <slug> <sha>` via
   `tools/Start-BobMrb.ps1`. Jeeves announces whatever lands.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\Start-BobMrbHandoff.ps1 `
  -Repo SimonBarnett/agentic_build -Issue N -Sha <pr-head> -Cwd C:\ai\agentic_build
```

Skill: `.grok/skills/bob-hostile-mrb`.
