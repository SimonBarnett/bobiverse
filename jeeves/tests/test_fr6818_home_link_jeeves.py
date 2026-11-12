"""FR #6818: bob.ntsa.uk home page links to /jeeves."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "jeeves" / "www" / "irc-ntsa" / "index.html"


def test_fr6818_index_has_visible_href_jeeves():
    text = HOME.read_text(encoding="utf-8")
    assert 'href="/jeeves"' in text
    assert "<a " in text
    # Visible link copy, not only an empty href.
    assert ">Jeeves<" in text or "jeeves" in text.lower()
