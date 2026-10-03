<!-- ARCHIVED COPY - source: SimonBarnett/bob-design-uat @ 1acf2a3, path .grok/skills/mrb-project-management/SKILL.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: mrb-project-management
description: >
  Project management for engineering MRBs on SimonBarnett/bob-design-uat:
  park feature requests in /docs, align to build-and-test-plan, ship worker
  PRs with BT0 evidence, Bob chairs MRB on the FR issue. Use when dispatching
  design-uat FRs, chairing product MRB, intake before build, or /mrb-project-management.
  Verdict and merge ritual defer to agentic_build bob-hostile-mrb. Workers do not
  stamp ready for human UAT.
---

# MRB project management (design-uat product)

This skill is **PM for engineering MRBs on this repo**. It does not replace
hostile review. For verdict, merge, and loop dispatch use
`SimonBarnett/agentic_build` skills `bob-hostile-mrb` and `bob-job-loop`.

Visual gates stay on `design-uat` G1-G3. This skill covers **how work enters
git and reaches MRB**.

## Locked rules

- **One FR issue** drives one worker PR. PR title includes `#<issue>`.
- **Intake:** GitHub issue labeled `feature-request` plus
  `docs/feature-request-<slug>-YYYY-MM-DD.md` on the branch (see
  `bob-spec-intake` on fleet).
- **Plan:** `docs/build-and-test-plan.md` definition of done for that issue.
- **Evidence:** BT0 before MRB — run
  `tools/Validate-DesignUatSkill.ps1` (exit 0); paste output on PR or MRB
  comment.
- **Chair:** Bob chairs MRB on the **feature-request issue** (e.g. #1, #49).
  Workers post `FAIL` or `PASS-nits` only via hostile MRB; never
  `ready for human UAT`.
- **Secrets:** no `password=` or API key assignments in git.

## Worker procedure

1. Read `docs/functional-spec.md`, the FR markdown, and
   `docs/build-and-test-plan.md` for the issue.
2. Work on a **non-main** branch; never push `main`; never merge own PR.
3. Implement only this FR's MUSTs; park adjacent holes with a **new** issue +
   doc (do not scope-creep a FIX).
4. Run BT0 locally or cite CI `.github/workflows/bt0.yml`.
5. Open PR; body has test summary (BT0 output + manual checklist rows). **No**
   UAT stamp.
6. Hand off hostile MRB (`Start-BobMrbHandoff` / `bob-job-loop` on fleet) with
   `-Docs` pointing at this FR and `-Plan docs/build-and-test-plan.md`.

## MRB PM checklist (Bob / dispatcher)

| Step | Check |
|------|--------|
| Intake | FR issue + `/docs` file exist; labels include `feature-request`. |
| Scope | PR diff matches FR MUST / MUST NOT; no unrelated FR bundled. |
| BT0 | Validator exit 0 on PR head (T-S07/T-S08 needles if applicable). |
| Missing features | Hostile MRB lists gaps; new FRs get intake doc before build. |
| Chair | MRB thread on FR issue; Bob only for human UAT stamp. |

## Related

| Skill | Repo | Role |
|-------|------|------|
| `design-uat` | this repo | G1-G3 visual UAT |
| `bob-hostile-mrb` | agentic_build | Hostile board, PASS-nits merge |
| `bob-job-loop` | agentic_build | Build + MRB until PASS-nits |
| `harvest-agent-skills` | agentic_build | Promote fleet playbooks (not product FRs) |

## Do not

- Write the full hostile MRB in the implementer session (Bob hands off).
- Implement harvest playbooks for IRC or fleet install here — use `agentic_irc`
  / `agentic_build`.
- Stamp ready for human UAT. Use `candidate PASS-UAT, Bob stamp required` only
  when the skill spec allows.
