# FR: CI-G2 Depends-on CI-G1 before wire

GitHub: #9323. Refs SimonBarnett/bobiverse#8841 and SimonBarnett/bobiverse#8839. Docs + stamp only.

CI-G2 (#8841) wires the open-children gate into `.github/workflows/build-jeeves.yml`. CI-G1 (#8839) owns the gate script. Architecture: `build-jeeves.yml -> open-children script -> fail list`. Offering #8841 while #8839 is still open with no script on main forces either a silent omit (S1 fail-when) or an omnibus script+wire PR.

## Goal

Stamp product `Depends-on: #8839` on #8841 so the chair skips CI-G2 until the gate script lands. Document the gate on main for later seats.

## Deliverables

- #8841 body top stamp is `Depends-on: #8839` (within the first 500 characters of the issue body).
- Comment on #8841 cites FR #9323 and the re-offer rule after #8839 closes on main.
- This docs mirror on main.
- Do not implement the open-children script or the build-jeeves wire in this card.

## Testable

- This mirror contains `#8839` and `#8841` and `#9323`.
- This mirror contains the architecture string `build-jeeves.yml -> open-children script`.
- This mirror says CI-G2 waits for CI-G1.
- No line starts with a closing keyword that names #8841 or #8839.

## Out of scope

- CI-G1 script implementation (#8839).
- CI-G2 workflow wire (#8841).
- BOB-G* / VIS-G* slices.
