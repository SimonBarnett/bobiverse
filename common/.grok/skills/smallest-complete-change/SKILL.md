---
name: smallest-complete-change
description: >
  Write the smallest change that fully solves the accepted FR or FIX:
  reuse existing helpers, the standard library, or an already-installed
  dependency before adding code; skip unasked features; leave a test for
  new non-trivial logic; never cut validation, error handling, or security.
  Use on FR and FIX implementation, when a job says "smallest change",
  "yagni", "simplest solution", or "do not over-engineer".
depends_on: []
---

# Smallest complete change

Adapted from Ponytail (MIT, Copyright (c) 2026 Dietrich Gebert,
https://github.com/DietrichGebert/ponytail). Fleet rules below win if they conflict.

For Bob Fleet FR and FIX seats. This does not change ACK/DONE, tests-first, or merge gates.
Implement the accepted issue as written. Do not push back on the request, switch session
modes, or wait for a human to pick an option.

## Before you write

Read the issue and the code it touches. List every place the change must reach: callers,
tests, fixtures, config, exports. Check what the change could break (data loss, exposure,
callers that stop working). That is scope. Extra features are not.

## Ladder

Take the first option that fully works:

1. Does it need to exist? Skip features, options and flexibility the issue did not ask
   for, and name them in the PR body.
2. Already in this codebase (helper, component, service, pattern)? Use it the way the
   surrounding code does.
3. Standard library or a platform feature? Use it, unless the project already has its own.
4. An installed dependency? Use it. Never add a dependency for a few lines.
5. Can it be one line a reader gets at a glance? One line. A one-liner that needs
   decoding is not short.
6. Otherwise: the minimum code that works.

## Rules

- Be lazy about the solution, never about the change: finish every part the task needs,
  including callers, tests and fixtures the change breaks.
- job-fr already requires tests first. New non-trivial logic (a branch, a loop, a parser,
  money or security, or a new script) must have a failing test before the implementation,
  then a passing one. Trivial changes need none beyond existing coverage.
- No abstraction, wrapper, option, config, or "for later" code nobody asked for.
  Deletion beats addition. Keep the structure the codebase already has.
- Bug fix: grep every caller of the function you touch, then fix the root cause once in
  the shared code.
- Code you move or merge keeps its error handling and validation.
- Between options of equal size, take the one that is correct on edge cases.
- Comment only the why the code cannot show, in one line.
- A deliberate shortcut with a known limit may use `shortcut: <the limit>, <when to upgrade>`.
  Prefer filing an FR when the limit matters to the fleet.

Never cut: validation at trust boundaries, error handling that prevents data loss,
security, accessibility, anything the issue asked for.

## Reply

In the PR body, end with one or two lines: what you skipped or did not check, and any
risk a reviewer must know.
