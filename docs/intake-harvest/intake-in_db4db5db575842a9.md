Lessons from redqueen-6240 airc MRB chain #7133/#7141/#7142/#7143/#7145/#7139:
1. Overlapping skill bullets: when CONFLICTING after sibling merge, fold origin/main and keep-both dated/FR skill bullets (DCC #7129 + SEAL #7131).
2. Local install origin/main can lag; fetch with refs/heads/main:refs/remotes/origin/main --force before behind/conflict checks.
3. If a stacked fix merges into the tip branch but refs/pull/N/head stays on the old SHA, do not assume GitHub will reattach — open a mainland fix PR targeting main immediately (class of #7142 -> #7155) rather than waiting on a stuck pull head.
4. Never resurrect AIRC_PRIORITY_FORM_VIA_EFORM after FR #6108; Session 0 SDK path is prepare-form verb / form_via_sdk only.
---
_via-intake id=`in_db4db5db575842a9` ts=`2026-11-13T19:49:53Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
