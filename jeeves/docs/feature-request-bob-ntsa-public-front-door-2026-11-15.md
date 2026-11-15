# Feature request: bob.ntsa.uk public visual system + HTML mocks (FR #7408)

Parent plan: Walrus public appliance polish 2026-11-15.
Live today: https://bob.ntsa.uk/ · https://mcp.ntsa.uk/
Prior art: FR #6453 static www, FR #6436 /jeeves settings, FR #6816 butler asset.

## Objective

Ship a shared **beautiful** visual system and HTML mocks for the bob.ntsa.uk / mcp.ntsa.uk public front door so later small FRs apply one coherent chrome (tokens, header/nav, cards) instead of one-off plain pages.

LOCKED

## Design note

**Charcoal + warm paper + butler gold.** Header is charcoal with a gold underline; body sits on warm paper; cards are near-white paper with soft borders. Primary nav: **Home · Downloads · Jeeves · MCP · GitHub**. Tokens live in `site.css` as `--charcoal`, `--ink`, `--paper`, `--gold` (and helpers). Same stylesheet is staged under `jeeves/www/site.css` for later live IIS/Amplify FRs and under `jeeves/docs/mocks/bob-ntsa-public-front-door/site.css` for the vision pack.

**Contrast / responsive:** Body ink on paper and nav paper/gold on charcoal remain readable. Mobile ≤400px checked against the mocks (`@media (max-width: 400px)` wraps nav under the brand without overlapping).

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Vision pack validates | `validate-vision-pack.py` exits 0 with `--mocks-dir` pointing at the front-door mocks | `python bob/agents/plan/tools/validate-vision-pack.py jeeves/docs/feature-request-bob-ntsa-public-front-door-2026-11-15.md --mocks-dir jeeves/docs/mocks/bob-ntsa-public-front-door` | non-zero exit or missing Shape/Success/mocks |
| S10 | Shared tokens + required mocks + nav | `site.css` defines `--ink`, `--gold`, `--charcoal`; mocks dir has `home.html`, `empty.html`, `error.html`; `home.html` nav links Downloads, Jeeves, MCP, GitHub | file content checks / `Select-String` / pytest pin `test_fr7408_public_front_door_mocks.py` | missing token, missing mock, or nav href absent |

## Shape

Primary (one): **website**

Hybrid note: public static HTML/CSS chrome for bob.ntsa.uk and mcp.ntsa.uk; live IIS/Amplify wiring is later FRs. Product core remains the Bob/Jeeves services.

LOCKED

## Screens

HTML mocks in `jeeves/docs/mocks/bob-ntsa-public-front-door/` (kebab-case). No PNGs.

| id | file | state |
|----|------|-------|
| M1 | home.html | primary |
| M2 | downloads.html | downloads catalogue |
| M3 | jeeves-commands.html | Jeeves cheat sheet |
| M4 | mcp-home.html | mcp.ntsa.uk entry |
| M5 | empty.html | empty catalogue |
| M6 | error.html | error |

## Stack

Default: static HTML5 + one shared CSS token file (no JS framework).

Why: public front door must stay fast, readable, and easy for later FRs to copy.

Why-not: SPA frameworks would delay FR-B+ IIS/Amplify work.

LOCKED

## Architecture

```
[browser] -> bob.ntsa.uk / mcp.ntsa.uk (static)
              site.css tokens + header/nav/cards
              later FR-B+: IIS/Amplify publish of these mocks
[services] bob/v1/* JSON APIs unchanged (out of scope)
```

LOCKED

## Out of scope

- Implementing live IIS/Amplify pages (FR-B+)
- Removing `:7701` (FR-E)
- Priority Agent download wiring (FR-I on priority-mcp)
- Filing sibling FRs in the same turn

## LOCKED

- Design tokens `--ink`, `--gold`, `--charcoal` (+ paper) in `site.css`
- Required mocks: home / empty / error (+ downloads, jeeves-commands, mcp-home)
- Nav: Home · Downloads · Jeeves · MCP · GitHub

## UNKNOWN

- Exact IIS vdir / Amplify route map (FR-B+)
- Final download catalogue entries (FR-I)