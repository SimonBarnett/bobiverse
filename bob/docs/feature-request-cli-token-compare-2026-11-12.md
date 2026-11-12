# Feature request: CLI token comparison on the appliance status page

Repo: `SimonBarnett/bobiverse`. Shape: service.

Vision: `bob/docs/vision-cli-token-compare-2026-11-12.md`
Spec: `bob/docs/functional-spec-cli-token-compare.md`
Mocks: `bob/docs/mocks/cli-token-compare/`
FR mirrors: `bob/docs/fr/cli-token-compare/`

## Success

See vision Success S1-S4.

## Not the pool pack

#6751 and siblings (including #6759 pool JSON) show remaining percent and drop token fields. Do not fold these slices into that pack, and do not add job token counts to GET /api/pools.

## Implementation issues (Refs, not a closing keyword)

- #6781 FR-001 Grok `modelUsage` on the DONE stamp
- #6782 FR-002 Cursor measured tokens, or `tokens=unknown`
- #6783 FR-003 ledger `job_costs.by_model`
- #6784 FR-004 appliance status token graph
- #6785 FR-005 `jeeves/VISION.md` hybrid note (docs). Shape stays service.

## Anti-omnibus

One GitHub issue per small FR. This docs PR parks mirrors only. Implementation issues stay open.
