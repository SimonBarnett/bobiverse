"""Hostile pin for MRB #6275 / FR #6274 docs hygiene.

C0 controls (BEL 0x07, FF 0x0c) must not eat letters in bob-ear.md
(auth.json / fetched_at / fresh=false). Contiguous product phrases stay intact.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EAR_DOC = ROOT / "bob" / "docs" / "bob-ear.md"


def test_mrb6275_fr6274_bob_ear_docs_no_c0_and_auth_json_contiguous():
    raw = EAR_DOC.read_bytes()
    assert b"**FR #6274 live weekly fetch:**" in raw
    i = raw.find(b"**FR #6274 live weekly fetch:**")
    line = raw[i : raw.find(b"\n", i)].replace(b"\r", b"")
    controls = sorted({c for c in line if c < 32})
    assert controls == [], f"C0 controls in FR #6274 docs line: {list(map(hex, controls))}"
    assert b"auth.json" in line
    assert b"\x07uth.json" not in raw
    assert b"fetched_at" in line
    assert b"fresh=false" in line
    assert b"cli-chat-proxy:/v1/billing?format=credits" in line
    assert b"Passive unified.jsonl is never posted as a fresh reading" in line
    # FR #6274 revisits blank-on-skip: keep last-good language present near 6270/6274
    assert b"do not blank a knowable value" in raw


def test_mrb6275_publish_prefers_live_billing_not_passive_log():
    import sys

    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bobreport

    src = Path(bobreport.__file__).read_text(encoding="utf-8")
    # publish_local_peer_fuel must call fetch_live_xai_weekly for the fresh path
    assert "fetch_live_xai_weekly(" in src
    assert "enrich_peer_keep_last_good_xai_weekly" in src
    start = src.find("def publish_local_peer_fuel")
    nxt = src.find("\ndef ", start + len("def publish_local_peer_fuel"))
    fn = src[start : nxt if nxt > start else start + 12000]
    assert "fetch_live_xai_weekly(" in fn
    # must not treat read_local_xai_weekly as the fresh publish path
    assert "xai = read_local_xai_weekly()" not in fn
