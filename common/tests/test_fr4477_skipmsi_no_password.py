"""FR #4477: a -SkipMsi airc stage must not contain a password file.

Real airc MSI packs still embed config/ergo.password (FR #4216).
-SkipMsi is a test stage, not a release artifact, and must not copy a live
Ergo PASS or write a placeholder password file into that stage.
"""

from __future__ import annotations

from pathlib import Path

PACK = Path(__file__).resolve().parents[1] / "scripts" / "Pack-BobiverseRelease.ps1"


def test_fr4477_skipmsi_does_not_embed_password_file():
    text = PACK.read_text(encoding="utf-8-sig")
    assert "FR #4477" in text
    assert "if ($SkipMsi) { $wantEmbedErgo = $false }" in text
    assert "FAKE_ERGO_PASS_FOR_SKIPMSI_STAGE" not in text
    # Release airc packs still embed (FR #4216).
    assert "$wantEmbedErgo = $EmbedErgoPassword -or ($Name -eq 'airc')" in text
