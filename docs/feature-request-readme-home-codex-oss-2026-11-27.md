# Feature request: Bobiverse README home polish (Codex for OSS)

**Repo:** SimonBarnett/bobiverse  
**Date:** 2026-11-27  
**Kind:** docs / home page (existing repo; no new product)  
**Related:** Codex for OSS application pack in this plan folder (`APPLICATION-codex-for-oss.md`)

## Objective

Visitors to https://github.com/SimonBarnett/bobiverse understand in under 30 seconds that Bobiverse is a **6GL**: plain-English intent, Git as the work store, IRC as the control surface, with Plan digests, deterministic Jeeves dispatch, and Bob agents that open PRs, run merge-review boards, and fix CI.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Above-the-fold pitch | First screen states 6GL + Plan / Jeeves / Bob + CLI matrix (xAI, Cursor, OpenAI; Codex upcoming) | Rendered GitHub README | First screen is MSI/sync/layout only |
| S2 | Screenshot strip | >=3 scrubbed images under `docs/assets/readme/` with captions | Images load on GitHub | Broken paths or secrets visible |
| S3 | Ops preserved | Existing pack/install/sync/behaviour content remains under Operator docs | Diff review | Ops sections deleted |
| S4 | About blurb | GitHub repo description matches hero (<=350 chars) | `gh repo view` description | Stale "Fleet IRC services: MSIs" only |
| S5 | No secrets | No tokens, passwords, private host policy leaks | Manual scrub of assets + markdown | Secret-like strings in PR |

LOCKED

## Shape

Primary: **service** (unchanged). This FR is documentation / GitHub home surface only.

LOCKED

## Gap vs origin/main

Current README is a strong fleet ops manual (MSI table, sparse work-tree sync, pack/install, behaviour). It does not lead with the product story OpenAI / investors need:

- 6GL / plain-English Git tool
- Plan digests with Gantt-style dependencies
- Deterministic Jeeves chair
- Bob PR / MRB / CI loop
- Multi-CLI matrix + Codex upcoming
- Live UI proof (tray + Halloy)

Repo signals (2026-11-27): ~9k commits, ~5.5k PRs, ~4.5k issues, release v2.0.1, 0 stars / 0 forks. Pitch must lead on maintenance intensity and innovation, not stars.

## Proposed change

1. Prepend concise hero (see `readme-draft.md` in this plan folder).
2. Add screenshot strip from `docs/assets/readme/`.
3. Relabel remaining depth as `## Operator docs` (keep substance).
4. Update GitHub About description in the same PR.

## Architecture (product loop for the hero)

```text
Human / Plan agent
  -> FR digest + Gantt deps
    -> Jeeves (deterministic chair, webhooks, !assign)
      -> IRC shop #{machine}
        -> Bob worker (Grok | Cursor | OpenAI | Codex...)
          -> PR -> MRB -> CI fix -> DONE
```

## Screenshots

| File | Caption |
|------|---------|
| `docs/assets/readme/01-bob-fleet-tray.png` | Bob Fleet tray: Agents (Grok / Cursor / OpenCode) and Plan |
| `docs/assets/readme/02-halloy-shop-wire.png` | Halloy shop wire: Jeeves assign and worker ACK |
| `docs/assets/readme/03-fleet-irc-presence.png` | Live fleet presence on IRC |

Source originals: `P:\My Pictures\bob\`. Scrub before merge if any private host/IP must stay out of public docs.

## Stack

Docs-only: Markdown + PNG assets in-repo. No new runtime dependency.

## Testable acceptance

- [ ] README hero visible without scrolling past MSI table on a typical GitHub desktop view
- [ ] Three screenshots render
- [ ] Operator docs still contain Pack, Install, Behaviour, Sync
- [ ] `gh api repos/SimonBarnett/bobiverse -q .description` matches new About blurb after PR merge (or follow-up)
- [ ] No secrets in diff

## Out of scope

- Submitting the OpenAI form (human)
- Wiring Codex CLI into `bob-worker` (separate FR)
- VERSION bump / release / MSI change

## Small slices

| id | title | file now? |
|----|-------|-----------|
| FR-001 | README hero + screenshots + Operator docs fold | Yes (this digest) |
| FR-002 | GitHub About description update | Checklist in FR-001 PR |
| FR-003 | Optional investor one-pager under `docs/` | Unfiled draft unless hero overflows |
