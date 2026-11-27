"""FR #10021: a second IRC write loss re-enters reconnect grace."""
from pathlib import Path

from repo_layout import ROOT

SRC = ROOT / "bob" / "scripts" / "bob_worker.py"


def test_fr10021_second_loss_logs_grace_and_recreates_outbox():
    text = SRC.read_text(encoding="utf-8")
    lost = text.index("def _on_irc_lost")
    body = text[lost:lost + 1800]
    assert "FR #10021" in body
    assert "already = bool(self._irc_reconnecting)" in body
    assert "if already:" in body
    recon = text.index("def _reconnect_loop")
    loop = text[recon:recon + 2200]
    assert loop.index("self._irc_reconnecting = False") < loop.index("self._after_irc_reconnect()")
    after = text.index("def _after_irc_reconnect")
    flush = text[after:after + 900]
    assert "ob.write_text" in flush
    assert "missing outbox" in flush
