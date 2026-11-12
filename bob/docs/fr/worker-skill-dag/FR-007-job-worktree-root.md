# FR-007 Assigned job-worktree skill root

GitHub: #6866. Stays open. Docs park Refs this issue.

## Goal

When the assigned job worktree exists, resolve can see that tree's `.grok/skills` and no other repo.

## Deliverables

- Optional extra root: the assigned worktree `.grok/skills` only.
- Refuse a root that is not that path.

## Testable

- A skill that exists only in the fixture worktree is returned for that job.
- A skill in a sibling repo path is not indexed.

## Out of scope

Scanning every clone on the box.
