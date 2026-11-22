"""FR #8991: out-of-fuel quit must remove the nick even when MessageBox cannot show."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_fr8991_quit_removes_before_dialog():
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    fn = src.index("def _quit_after_out_of_fuel")
    body = src[fn:src.index("\n    def ", fn + 10)]
    remove = body.index("post_digest_worker_remove")
    dialog = body.index("show_out_of_fuel_dialog")
    shutdown = body.index('self.shutdown("fuel-exhausted"')
    assert remove < dialog < shutdown


def test_fr8991_messagebox_is_threaded():
    src = (ROOT / "bob" / "scripts" / "bob_worker.py").read_text(encoding="utf-8")
    fn = src.index("def show_out_of_fuel_dialog")
    body = src[fn:src.index("\ndef ", fn + 10)]
    assert 'name="out-of-fuel-dialog"' in body
    assert "th.join(5.0)" in body
