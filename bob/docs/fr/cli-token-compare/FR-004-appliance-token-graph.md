# FR-004 Appliance status token graph

GitHub: #6784. Stays open. Docs park Refs this issue. Pool pack #6759 is a different surface.

## Goal

The Jeeves appliance status page shows measured tokens by model, an empty state, and an error state.

## Deliverables

- Read-only use of the `by_model` rollup from FR-003.
- Inline SVG on the existing status HTML. Same auth as `/status`.
- Home: one series per model. Unknown count is text, not a zero bar.
- Empty: no measured rows, no zero series.
- Error: ledger unreadable, no invented series.
- Wireframes: `bob/docs/mocks/cli-token-compare/home.html`, `empty.html`, `error.html`.

## Testable

`pytest` renders the three HTML bodies. Empty output has no zero-length data series. Error output does not contain a bar series.

## Out of scope

New frontend host, chart SaaS, login changes, and writing the ledger.
