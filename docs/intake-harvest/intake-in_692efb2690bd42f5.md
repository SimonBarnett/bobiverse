FR #7778 / PR #7830. bob/scripts/bob_worker.py build_launch applied worker_start_model.launch_argv_with_model/effort to the whole argv, and those helpers insert at index 1, so --reasoning-effort/--model landed ahead of the FR #2699 shared prefix. That broke test_fr2699_plan_no_auto_update and test_mrb2710_hostile_plan_no_auto_update for every grok mode. Playbook: when a helper prepends CLI flags, apply it to the tail [exe] + argv[len(prefix):] and re-attach prefix, so --no-auto-update/--no-alt-screen/--cwd stays at argv[1:4].
---
_via-intake id=`in_692efb2690bd42f5` ts=`2026-11-16T00:12:58Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
