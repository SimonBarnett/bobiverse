# BOB-56 / FR #8705 evidence: bob.ntsa.uk docs tray Agents/Workers

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8705
**Slice:** bob.ntsa.uk docs: tray Agents/Workers (Success S1)
**Depends-on:** BOB-06 (menu tree; soft — docs pin the mock tree)

## S1

Docs describe the new tray menu and match the menu tree.

## How measured

1. `jeeves/www/irc-ntsa/docs/tray/index.html` lists Status, Agents{Plan, Priority, Jeeves}, Workers{Grok, Cursor, Open Code}, Weights, About, Exit.
2. Home `jeeves/www/irc-ntsa/index.html` links to `docs/tray/index.html`.
3. Labels align with `bob/docs/mocks/systray-agents-workers/home.html` (BOB-06).
4. Tests: `jeeves/tests/test_fr8705_docs_tray_agents_workers.py`.

## Fail-when

Stale menu docs (flat Plan sibling or missing Weights/Exit / Agents / Workers children).

## Live note

Static HTML ships with the site tree; IIS publish still needs operator `Install-BobWebhooks` (or equivalent) before bob.ntsa.uk shows the page.
