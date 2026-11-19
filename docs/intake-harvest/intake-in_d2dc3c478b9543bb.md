what: In MRB #8231 (FR #8230 fleet Go fuel), the new hostile test test_mrb8231_public_digest_path_without_env let bob_home.digest_home() resolve the host's real ~/.bobiverse/digest.json, which shadowed the tmp install_root candidate (1 of 7 failed).
where: bob/tests/test_fr8230_fleet_go_fuel.py
fix: redirect USERPROFILE/HOME in the no-env test so the install-home fallback is exercised hermetically (commit a2a70834). Re-ran: 7 passed.
lesson: no-env home/digest-path tests must isolate USERPROFILE/HOME; an existing host ~/.bobiverse/digest.json shadows tmp install-home candidates.
---
_via-intake id=`in_d2dc3c478b9543bb` ts=`2026-11-18T18:23:27Z`_
_source machine=`redqueen` agent=`Report-BobiverseIntakeIssue` book=`harvest` ver=`-`_
