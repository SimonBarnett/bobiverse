# Index: AIRC-HIDE — Services.msc hide + native host (no nssm)

**Repo:** SimonBarnett/bobiverse  
**Date:** 2026-11-22  
**Mode:** park-only + **fr-digest** go-gate + hold  
**Theme vision:** [feature-request-airc-hide-services-msc-2026-11-22.md](./feature-request-airc-hide-services-msc-2026-11-22.md)

## Digest

| Kind | Issue | Title |
|------|-------|-------|
| Digest | [#9128](https://github.com/SimonBarnett/bobiverse/issues/9128) | Digest: AIRC-HIDE — Services.msc hide + native host (no nssm) |

Labels on digest: `fr-digest`, `hold`, `feature-request`.  
Unhold digest alone releases children (when BOB-G live); until then `hold` is the gate.

## Children

| ID | Issue | Title | Doc | Intra Depends-on |
|----|-------|-------|-----|------------------|
| AIRC-HIDE-01 | [#9129](https://github.com/SimonBarnett/bobiverse/issues/9129) | SYSTEM status/control helper for Airc | [feature-request-airc-hide-01-system-helper-2026-11-22.md](./feature-request-airc-hide-01-system-helper-2026-11-22.md) | #9128 |
| AIRC-HIDE-02 | [#9130](https://github.com/SimonBarnett/bobiverse/issues/9130) | Native SCM host — no NSSM | [feature-request-airc-hide-02-native-scm-2026-11-22.md](./feature-request-airc-hide-02-native-scm-2026-11-22.md) | #9128, #9129 |
| AIRC-HIDE-03 | [#9131](https://github.com/SimonBarnett/bobiverse/issues/9131) | Apply SO Services.msc hide SDDL | [feature-request-airc-hide-03-sddl-msc-2026-11-22.md](./feature-request-airc-hide-03-sddl-msc-2026-11-22.md) | #9128, #9130 |
| AIRC-HIDE-04 | [#9132](https://github.com/SimonBarnett/bobiverse/issues/9132) | Fleet scripts off Get-Service / NSSM | [feature-request-airc-hide-04-fleet-scripts-2026-11-22.md](./feature-request-airc-hide-04-fleet-scripts-2026-11-22.md) | #9128, #9129, #9130 |
| AIRC-HIDE-05 | [#9133](https://github.com/SimonBarnett/bobiverse/issues/9133) | Docs + skills + VISION S1 | [feature-request-airc-hide-05-docs-skills-2026-11-22.md](./feature-request-airc-hide-05-docs-skills-2026-11-22.md) | #9128, #9131, #9132 |

## Merge / offer order

`01 → 02 → (03 ∥ 04) → 05`

## Notes

- **Services.msc:** SO full hide SDDL (even elevated admins).
- **Task Manager:** no `nssm.exe` host; `airc.exe` listed is OK; true hide out of scope.
- Park-only until human unholds digest.
- SO: https://stackoverflow.com/questions/25736268/how-to-register-a-windows-service-but-avoid-it-being-listed-in-the-services-cons
