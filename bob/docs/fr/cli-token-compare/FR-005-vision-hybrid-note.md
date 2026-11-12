# FR-005 Chair vision names the appliance status companion

GitHub: #6785. Docs only. Do not close #6781 #6782 #6783 #6784 from this note.

## Goal

`jeeves/VISION.md` names the existing appliance status page as a chair companion. The product shape stays service.

## Deliverables

- Hybrid note under Shape states that ircJeeves is the product and the appliance status page is a companion.
- The Shape primary line stays service.
- The line that says companions are not a website is replaced so it no longer denies the status page that already ships.
- Docs only. No chair code.

## Testable

`jeeves/tests` vision pin (same style as `test_fr5090_jeeves_vision.py`) asserts the hybrid note names the appliance status companion and the primary shape is still service. UTF-8, no BOM.

## Out of scope

Token graphs, ledger code, and closing FR-001 through FR-004. A later docs park Refs those issues.
