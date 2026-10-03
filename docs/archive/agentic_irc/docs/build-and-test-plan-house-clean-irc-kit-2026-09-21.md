<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/build-and-test-plan-house-clean-irc-kit-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: house-clean IRC kit

**Date:** 2026-09-21
**FR:** `docs/feature-request-house-clean-irc-kit-2026-09-21.md`
**Issue:** https://github.com/SimonBarnett/agentic_irc/issues/34
**Profile:** generic
**Do not:** join Libera from CI, print connect.password, productise, push `main`, MRB in-session.

## Work tree

Branch `work/<jobId>` off current `main`. Open a PR. Never push `main`.

## Steps

1. Set GitHub repo description to match README (Ergo fleet, not Libera-first). If the worker cannot edit About, say so on the issue for Simon.
2. README first paragraph: one fleet sentence (`irc.ntsa.uk:6697` `#bobiverse`). Libera SASL stays under a `## Legacy Libera` heading.
3. Align nick table with `https://github.com/SimonBarnett/agentic_build` `config/bobiverse.json` + `docs/bobiverse.md`. Record alias `ce-priority-dev1` / `dev1` / `bob-dev1`.
4. `docs/README.md` index: live vs historical MRB. Point `bob-irc` only at live docs.
5. Add `docs/tofu-rotation.md` from the FR drill. Wire or extend pytest for AGPK mismatch + inbox id skip (do not open a socket to any IRC network).
6. Guard text on DUMB / Mode 3: not a git-task worker; `--operators` required; no Win95 TLS claim.
7. MODE2 vs floor: one paragraph in README extensions.

## Prove

```bash
pip install -r requirements.txt pytest
pytest -q
```

CI already runs pytest + moot-thin + dumb-dotnet. Do not add a job that connects to `irc.ntsa.uk` or Libera.

## Done when

- PR open; FR + plan on the branch.
- pytest green offline.
- PR URL commented on issue #34. Wait for handed-off MRB.
- FAIL → FIX PR. PASS-nits → MRB agent merges. Only Bob stamps UAT.
