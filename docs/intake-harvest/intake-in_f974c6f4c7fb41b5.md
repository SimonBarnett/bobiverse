what: test_fr3180_idle_stale_keeps_running_announces asserted post_bored() is False and no !bored, but FR #7834 changed a stale build to still send !bored and take work (post_bored returns True), leaving main red. where: bob/tests/test_fr3180_manual_only_seat_starts.py (old line 153). evidence: test_fr2782_stale_build_recycle.py asserts post_bored() is True; bob_worker.py post_bored (FR #7834) returns True and sends !bored. fix: updated the test to the FR #7834 contract and set a stale_build_reporter so the assertion does not hit the default crash_report path. FR SimonBarnett/bobiverse#8419.
---
_via-intake id=`in_f974c6f4c7fb41b5` ts=`2026-11-20T14:27:32Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
