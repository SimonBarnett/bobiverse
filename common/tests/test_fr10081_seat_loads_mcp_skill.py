"""FR #10081: seat start reads the skill over HTTPS, not from git."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bob_seat_skills as seat  # noqa: E402

SRC = ROOT / "scripts" / "bob_seat_skills.py"


COPY = ROOT.parent / "bob" / "tray" / "src" / "Private" / "Copy-BobProjectSkills.ps1"
AGENTS = ROOT.parent / "bob" / "agents" / "worker" / "AGENTS.md"


def test_worker_start_loads_dag_not_git():
    text = COPY.read_text(encoding="utf-8")
    assert "FR #10081" in text
    assert "https://bob.ntsa.uk/mcp" in text
    assert "get_skill" in text
    assert "list_catalog" in text
    assert "git clone" not in text.lower()
    assert "Copy-Item $src" not in text
    agents = AGENTS.read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/mcp" in agents
    assert "Do not `git clone`" in agents


def test_source_does_not_fetch_git():
    text = SRC.read_text(encoding="utf-8")
    assert "FR #10081" in text
    assert "git clone" not in text
    assert "sparse-checkout" not in text
    assert "get_skill" in text
    assert "https://bob.ntsa.uk/mcp" in text


def test_load_seat_skill_uses_mcp_body():
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            doc = {"name": "bob-shop", "skillMd": "# Shop\n\nfrom-mcp\n"}
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": json.dumps(doc)}]},
            }
            return json.dumps(payload).encode("utf-8")

    def opener(request, timeout=0):
        seen["url"] = request.full_url
        seen["body"] = request.data.decode("utf-8")
        return _Resp()

    md = seat.load_seat_skill("bob-shop", url="https://bob.ntsa.uk/mcp", opener=opener)
    assert md.startswith("# Shop")
    assert "from-mcp" in md
    assert seen["url"] == "https://bob.ntsa.uk/mcp"
    assert "get_skill" in seen["body"]
    assert "bob-shop" in seen["body"]
