"""FR #7086: !build release is idempotent when gh tag/release already exists."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bobiverse_build as bb  # noqa: E402


def _cp(rc=0, out="", err=""):
    return SimpleNamespace(returncode=rc, stdout=out, stderr=err)


def test_fr7086_existing_prerelease_uploads_assets_instead_of_failing():
    seen = []

    def gh(args, **k):
        seen.append(args)
        if args[1] == "release" and args[2] == "create":
            return _cp(
                1,
                "",
                "gh release create failed: a release with the same tag name already exists: v2.0.0\n",
            )
        if args[1] == "release" and args[2] == "view":
            return _cp(0, json.dumps({"isPrerelease": True, "url": "https://example.test/v2.0.0"}))
        if args[1] == "release" and args[2] == "upload":
            return _cp(0, "")
        if args[1] == "api":
            return _cp(0, "v9.9.9\n")
        return _cp(1, "", "unexpected")

    fn = bb.make_github_prerelease_fn("o/r", target_sha="abc", title="t", notes="n", gh_runner=gh)
    out = fn(tag="v2.0.0", assets=["bob-2.0.0.msi"], prerelease=True, latest=False)
    assert out["url"] == "https://example.test/v2.0.0"
    verbs = [(a[1], a[2]) for a in seen]
    assert ("release", "create") in verbs
    assert ("release", "upload") in verbs
    upload = next(a for a in seen if a[1] == "release" and a[2] == "upload")
    assert "v2.0.0" in upload and "--clobber" in upload and "bob-2.0.0.msi" in upload


def test_fr7086_existing_non_prerelease_still_refused():
    def gh(args, **k):
        if args[1] == "release" and args[2] == "create":
            return _cp(1, "", "a release with the same tag name already exists: v2.0.0")
        if args[1] == "release" and args[2] == "view":
            return _cp(0, json.dumps({"isPrerelease": False, "url": "u"}))
        return _cp(0, "")

    fn = bb.make_github_prerelease_fn("o/r", target_sha="abc", title="t", notes="n", gh_runner=gh)
    try:
        fn(tag="v2.0.0", assets=[], prerelease=True, latest=False)
    except RuntimeError as e:
        assert "pre-release" in str(e).lower() or "prerelease" in str(e).lower()
    else:
        raise AssertionError("expected refusal of an existing full release")


def test_fr7086_other_create_errors_still_fail():
    def gh(args, **k):
        if args[1] == "release" and args[2] == "create":
            return _cp(1, "", "HTTP 401: Bad credentials")
        return _cp(0, "")

    fn = bb.make_github_prerelease_fn("o/r", target_sha="abc", title="t", notes="n", gh_runner=gh)
    try:
        fn(tag="v2.0.0", assets=[], prerelease=True, latest=False)
    except RuntimeError as e:
        assert "401" in str(e) or "credentials" in str(e).lower()
    else:
        raise AssertionError("expected create failure to propagate")
