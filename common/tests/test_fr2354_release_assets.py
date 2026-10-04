"""FR #2354: release must publish bob/airc/jeeves MSI + sha256 assets."""
from __future__ import annotations


REQUIRED_PRODUCTS = ("bob", "airc", "jeeves")


def required_release_assets(version: str, products=REQUIRED_PRODUCTS) -> list[str]:
    ver = str(version or "").strip().lstrip("v")
    if not ver:
        raise ValueError("version required")
    out: list[str] = []
    for p in products:
        out.append(f"{p}-{ver}.msi")
        out.append(f"{p}-{ver}.msi.sha256")
    return out


def missing_release_assets(asset_names, version: str, products=REQUIRED_PRODUCTS) -> list[str]:
    have = set(str(x) for x in (asset_names or []))
    return [n for n in required_release_assets(version, products) if n not in have]


def test_fr2354_required_assets_for_0_1_22():
    names = required_release_assets("0.1.22")
    assert "airc-0.1.22.msi" in names
    assert "airc-0.1.22.msi.sha256" in names
    assert "bob-0.1.22.msi" in names
    assert "jeeves-0.1.22.msi" in names
    assert len(names) == 6


def test_fr2354_missing_detects_bob_only_release():
    bob_only = ["bob-0.1.22.msi", "bob-0.1.22.msi.sha256"]
    miss = missing_release_assets(bob_only, "v0.1.22")
    assert "airc-0.1.22.msi" in miss
    assert "airc-0.1.22.msi.sha256" in miss
    assert "jeeves-0.1.22.msi" in miss
    assert "bob-0.1.22.msi" not in miss


def test_fr2354_complete_release_has_no_missing():
    complete = required_release_assets("0.1.22")
    assert missing_release_assets(complete, "0.1.22") == []