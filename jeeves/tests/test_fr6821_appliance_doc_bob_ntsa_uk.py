"""FR #6821 / FR-012: appliance doc operator URL is https://bob.ntsa.uk/jeeves."""
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "jeeves" / "docs" / "jeeves-settings-appliance.md"


def _text() -> str:
    raw = DOC.read_bytes()
    assert raw[:3] != b"\xef\xbb\xbf"
    return raw.decode("utf-8")


def test_fr6821_doc_states_bob_ntsa_uk_jeeves():
    text = _text()
    assert "https://bob.ntsa.uk/jeeves" in text


def test_fr6821_doc_does_not_tell_operator_to_browse_jeeves_ntsa_uk():
    text = _text()
    low = text.lower()
    assert "browse **https://jeeves.ntsa.uk" not in low
    assert "browse https://jeeves.ntsa.uk" not in low
    assert "operator url: **https://jeeves.ntsa.uk" not in low


def test_fr6821_doc_does_not_forbid_publishing_ui_on_bob_ntsa_uk():
    text = _text()
    low = text.lower()
    assert "do **not** front it via `bob.ntsa.uk`" not in low
    assert "never put this behind cloudflare, `bob.ntsa.uk`" not in low
    assert "not to publish the ui on bob.ntsa.uk" not in low
