# BOB-TRAY-UI-09 / FR #9270 evidence: Jeeves butler from bob.ntsa.uk

**Slice:** Agents > Jeeves shows butler from bob.ntsa.uk cache or offline fallback (Success S1)

## S1

Jeeves menu item uses the butler icon.

| Source | Path |
|--------|------|
| Online cache (preferred) | `<install>/assets/jeeves-butler.ico` filled from `https://bob.ntsa.uk/jeeves/assets/jeeves-butler.ico` on first online load |
| Offline fallback | `jeeves/assets/jeeves-butler.ico` beside the install/repo root |

TipForm (`ResolveJeevesButlerIcon`) and PowerShell (`Resolve-BobTrayJeevesButlerIcon` in `BobTrayJeevesButler.ps1`) share that order. Fetch uses a short HttpWebRequest timeout; `BOB_JEEVES_BUTLER_SKIP_FETCH=1` or `-SkipFetch` skips the network (tests). `BOB_JEEVES_BUTLER_URL` overrides the download URL.

## How measured

- Tests: `bob/tests/test_fr9270_jeeves_butler_bob_ntsa.py`
- Offline: `Test-Path` / ICO magic on `jeeves/assets/jeeves-butler.ico`
- Cache preference harness with `-SkipFetch`

## Out of scope

- Other BOB-TRAY-UI children
- Changing Jeeves start behaviour
