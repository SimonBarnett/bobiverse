"""FR #10020: cursor agent exit 0 ends the seat. It must not keep !bored."""
from repo_layout import ROOT

SRC = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")


def test_fr10020_zero_exit_shuts_down_before_any_bored():
    mark = SRC.index("FR #7593: zero exit ends the seat")
    body = SRC[mark:mark + 2800]
    leave = body.index('self.log("agent: zero exit; leaving (a closed agent ends the seat)")')
    after = body[leave:]
    shut = after.index('self.shutdown("agent-exited", EXIT_OK)')
    assert shut < 200
    assert "self.post_bored" not in after[:shut]
    assert "bored -> shop" not in after[:shut]
