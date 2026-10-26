"""FR #4998: BOM-less common scripts touched by FR #4988 stay pure ASCII."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [
    ROOT / "common" / "scripts" / "Bobiverse-Common.ps1",
    ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1",
]


def test_fr4988_scripts_bomless_ascii():
    for path in SCRIPTS:
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"BOM in {path.name}"
        bad = [i for i, b in enumerate(raw) if b > 127]
        assert bad == [], f"non-ASCII in {path.name} at {bad[:10]}"
