MRB #6809: local branch docs/mrb-6809-hostile created earlier from origin/main; later `git push -u origin docs/mrb-6809-hostile` from a different worktree pushed that stale branch (opened bad PR #6824). Fix: delete stale local/remote branch, recreate from tip `origin/fr-N`, `git push -u origin HEAD:docs/mrb-N-hostile`. Closed #6824; clean #6827.
---
_via-intake id=`in_ffc2ee825d1b4c98` ts=`2026-11-12T13:05:43Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
