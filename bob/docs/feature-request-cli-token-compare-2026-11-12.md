# Feature request: CLI token comparison on the appliance status page

Repo: `SimonBarnett/bobiverse`. Shape: service.

Vision: `bob/docs/vision-cli-token-compare-2026-11-12.md`
Spec: `bob/docs/functional-spec-cli-token-compare.md`
Mocks: `bob/docs/mocks/cli-token-compare/` and `bob/docs/mocks/jeeves-login/`
FR mirrors: `bob/docs/fr/cli-token-compare/`

## Success

See vision Success S1-S5. S5 is the login page at https://bob.ntsa.uk/jeeves. #6757 (PR #6791) landed the old hostname and stays closed.

## Not the pool pack

#6751 and siblings (including #6759 pool JSON) show remaining percent and drop token fields. Do not fold these slices into that pack, and do not add job token counts to GET /api/pools.

## Implementation issues (Refs, not a closing keyword)

- #6781 FR-001 Grok `modelUsage` on the DONE stamp
- #6782 FR-002 Cursor measured tokens, or `tokens=unknown`
- #6783 FR-003 ledger `job_costs.by_model`
- #6784 FR-004 appliance status token graph
- #6785 FR-005 `jeeves/VISION.md` hybrid note (docs). Shape stays service.
- #6798 FR-006 was the login bundle. It is closed. Implement the six slices.
- #6815 FR-007 GET /jeeves returns the login page and is not a 403
- #6816 FR-008 login page shows jeeves/assets/jeeves-butler.ico
- #6818 FR-009 Bob home page links to /jeeves
- #6819 FR-010 login form uses the existing session login
- #6820 FR-011 settings and status stay behind the session cookie
- #6821 FR-012 appliance doc states https://bob.ntsa.uk/jeeves

## Anti-omnibus

One GitHub issue per small FR. This docs PR parks mirrors only. Implementation issues stay open.
