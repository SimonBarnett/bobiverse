what: Test-HarvestRecentLessonDedup treated a CLOSED unmerged (MRB-rejected) harvest-lesson PR as a cover for a corrected sentence. where: common/scripts/Invoke-BobiverseHarvest.ps1. fix: Test-HarvestPrClosedUnmarked skips state=CLOSED with mergedAt null; only OPEN and MERGED tips cover a lesson. Landed via FR #8368.
---
_via-intake id=`in_fed0419de0cb457f` ts=`2026-11-19T14:49:44Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
