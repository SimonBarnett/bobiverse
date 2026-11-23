"""FR #7478: webhook docs generator emits logo chrome and does not overwrite home."""
from __future__ import annotations

from pathlib import Path

import gen_bob_webhook_docs_html as gen


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def test_fr7478_generator_parity_and_skips_home(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[2]
    checked = repo / "jeeves" / "www" / "irc-ntsa" / "docs" / "webhooks"

    def _www(_root: Path) -> Path:
        return tmp_path

    monkeypatch.setattr(gen.d, "www_root", _www)
    gen.main()

    assert not (tmp_path / "index.html").exists(), "generator must not write redesigned home"
    names = sorted(p.name for p in (tmp_path / "docs" / "webhooks").glob("*.html"))
    checked_names = sorted(p.name for p in checked.glob("*.html"))
    # Hand stubs (digest-local redirect, models-validate retired notice) are not
    # registry-generated; generator output must still match for every emitted page.
    # FR #8835 models + builds; FR #8820 refresh lives on models.html (no models-validate page).
    hand_stubs = {"digest-local.html", "models-validate.html"}
    assert set(names) == set(checked_names) - hand_stubs
    assert hand_stubs <= set(checked_names)
    assert "models-validate.html" not in names
    assert "models.html" in names and "builds.html" in names
    for name in names:
        got = _norm((tmp_path / "docs" / "webhooks" / name).read_text(encoding="utf-8"))
        want = _norm((checked / name).read_text(encoding="utf-8"))
        assert got == want, f"generator drift on {name}"
        assert 'class="brand"' in got
        assert 'src="/jeeves/assets/ntsa-gut-logo.png"' in got
        assert 'rel="icon"' in got
