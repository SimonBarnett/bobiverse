<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-mrb-separate-docs-pr-fr348-2026-09-26.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR #348: MRB docs step uses a separate docs PR

**Issue:** https://github.com/SimonBarnett/agentic_build/issues/348

## Rule

MRB never pushes commits onto the PR under review. After PASS, stale docs go in
exactly one separate branch/PR named like `docs/mrb-<n>-...` that references the
original, then merge original + docs PR (or docs-only if already merged). FAIL
fixes stay on one separate fix PR (unchanged).

## Guard

```powershell
python tools/mrb_docs_branch_guard.py --repo OWNER/REPO --pr N --self-test
python tools/mrb_docs_branch_guard.py --repo OWNER/REPO --pr N --json
# exit 2 = docs(MRB on feature branch or foreign commit after MRB start
```
