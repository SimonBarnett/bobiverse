"""MRB #5013 fix: no embedded RSA private key PEM in airc_dcc_bulk (GitGuardian)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DCC = (ROOT / "airc" / "scripts" / "airc_dcc_bulk.py").read_text(encoding="utf-8")


def test_no_embedded_rsa_private_key_pem():
    assert "BEGIN RSA PRIVATE KEY" not in DCC
    assert "BEGIN PRIVATE KEY" not in DCC
    assert "_DEFAULT_TLS_KEY_PEM" not in DCC
    assert "_generate_ephemeral_tls_pem" in DCC
    assert "AIRC_DCC_TLS_CERT" in DCC


def test_ephemeral_tls_roundtrip_still_works():
    import airc_dcc_bulk as dcc

    payload = b"mrb5013-ephemeral-" + b"x" * 256
    line, body, dig = dcc.dcclisten_helper_roundtrip(payload, tls=True, timeout_s=8.0)
    assert body == payload
    assert dig == dcc.sha256_hex(payload)
    assert "tls=1" in line
