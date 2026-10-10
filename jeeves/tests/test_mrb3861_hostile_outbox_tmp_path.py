"""docs/mrb-3861: hostile pins for harvest OutboxDir tmp_path lesson."""
from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
    / "SKILL.md"
)


def test_mrb3861_harvest_outbox_dir_tmp_path_lesson_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert (
        "Harvest pytest OutboxDir: always use tmp_path / harvest-outbox; "
        "never hardcode D:/bobfleet job paths (hosts without D: fail New-Item)."
    ) in text
    # no BOM
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_mrb3861_fr3859_product_pin_still_on_main():
    pin = (
        Path(__file__).resolve().parents[2]
        / "common"
        / "tests"
        / "test_fr3827_harvest_skip_fail_supersede_cast_iron.py"
    )
    src = pin.read_text(encoding="utf-8")
    assert 'tmp_path / "harvest-outbox"' in src
    assert src.count("tmp_path: Path") >= 2