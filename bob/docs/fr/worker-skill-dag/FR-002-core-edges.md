# FR-002 depends_on edges on the worker core skills

GitHub: #6861. Stays open. Docs park Refs this issue.

## Goal

Declare `depends_on` on the existing worker core skills so an FR job pulls the wire skill and does not pull UAT.

## Deliverables

- Frontmatter `depends_on` on the worker seat, job-irc, job-fr, job-mrb, job-uat, and harvest skills that already ship in the worker pack.
- Edges only. No new lesson prose.

## Testable

- A fixture or the real frontmatter parses.
- job-fr lists job-irc.
- job-uat is not a dependency of job-fr.

## Out of scope

Rewriting skill bodies. Product repos other than the edges named here.
