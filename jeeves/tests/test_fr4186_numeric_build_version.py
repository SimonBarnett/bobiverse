"""#4186: !build refuses non-numeric versions (WiX needs numeric ProductVersion)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common" / "scripts"))
import bobiverse_build as bb  # noqa: E402
import chair_commands  # noqa: E402


class _Lock:
    def __init__(self):
        self.acquired = []

    def try_acquire(self, repo, bid):
        self.acquired.append(repo)
        return True, bid


@pytest.mark.parametrize("v", ["0.1.32", "0.1.32.1"])
def test_numeric_versions_accepted(v):
    assert bb.version_refusal(v) is None


@pytest.mark.parametrize("v", ["0.1.32-test2", "v0.1.32", "", "0.1", "0.1.32.1.2", "0.1.x"])
def test_non_numeric_versions_refused(v):
    line = bb.version_refusal(v)
    assert line and "refused" in line and "numeric" in line


@pytest.mark.parametrize("v", ["0.1.32-test2", "v0.1.32"])
def test_decide_build_refuses_before_lock_or_recipe(v):
    lock = _Lock()
    loads = []
    dec = bb.decide_build(
        who=object(), body=f"!build SimonBarnett/bobiverse {v}",
        may=lambda *a: True, denied_line=lambda c: "denied",
        recipe_loader=lambda r: loads.append(r), lock=lock,
    )
    assert dec is not None and not dec.ok and dec.reason == "bad_version"
    assert not dec.route and not lock.acquired and not loads
    assert "numeric" in dec.pm_lines[0]


def test_decide_build_empty_version_not_queued():
    lock = _Lock()
    dec = bb.decide_build(
        who=object(), body="!build SimonBarnett/bobiverse",
        may=lambda *a: True, denied_line=lambda c: "denied",
        recipe_loader=lambda r: None, lock=lock,
    )
    assert dec is not None and not dec.ok and not dec.route and not lock.acquired


@pytest.mark.parametrize("v", ["0.1.32", "0.1.32.1"])
def test_decide_build_queues_numeric(v):
    lock = _Lock()
    dec = bb.decide_build(
        who=object(), body=f"!build SimonBarnett/bobiverse {v}",
        may=lambda *a: True, denied_line=lambda c: "denied",
        recipe_loader=lambda r: bb.BuildRecipe(machine="ionos"), lock=lock,
        new_build_id=lambda: "b-1",
    )
    assert dec.ok and dec.route == f"BUILD v1 repos=SimonBarnett/bobiverse version={v} ref=HEAD"


def test_help_documents_numeric_version():
    text = Path(chair_commands.__file__).read_text(encoding="utf-8")
    assert "x.y.z or x.y.z.w" in text
