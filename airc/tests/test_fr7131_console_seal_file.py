"""FR #7131: airc console receives agentic-file SEAL (tier S) without python.exe."""
from __future__ import annotations

import hashlib
from pathlib import Path

import airc_console as ac
import airc_seal_file as sf
import filexfer
import seal
from airc_auth_helpers import ops_auth

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "airc" / "scripts" / "Build-Airc.ps1"


def _core(tmp_path: Path) -> ac.AircConsoleCore:
    auth = ops_auth("op", channel="#tm")
    return ac.AircConsoleCore(
        machine="tm",
        auth=auth,
        nick="tm_console",
        shell_runner=None,
        console_home=tmp_path,
    )


def _priv(src: str, target: str, body: str) -> str:
    return f":{src}!u@h PRIVMSG {target} :{body}"


def test_fr7131_identity_mints_under_console_home(tmp_path):
    ident = sf.ensure_identity(tmp_path)
    path = tmp_path / "identity.json"
    assert path.is_file()
    assert ident.get("pk")
    again = sf.ensure_identity(tmp_path)
    assert again["pk"] == ident["pk"]
    line = sf.agpk_line(ident)
    assert line.startswith("AGPK v1 ")
    assert seal.parse_agpk_line(line)


def test_fr7131_channel_agpk_pins_without_auth(tmp_path):
    core = _core(tmp_path)
    other = seal.genkey(tmp_path / "sender-ident.json")
    hr = core.handle_raw(_priv("bob-marchhare", "#tm", f"AGPK v1 {other['pk']}"))
    assert hr is not None
    assert hr.action == "seal_file"
    peers = seal.load_peers(tmp_path / "peers.json")
    assert peers["bob-marchhare"]["pk"] == other["pk"]


def test_fr7131_file_offer_s_accepts_m_refuses(tmp_path):
    core = _core(tmp_path)
    fid = "aabbccddaabbccdd"
    h = "a" * 64
    offer_s = f"FILE v1 OFFER tm_console bob-mh {fid} 12 {h} S secret.txt"
    hr = core.handle_raw(_priv("bob-mh", "#tm", offer_s))
    assert hr and hr.action == "seal_file"
    assert hr.reply == f"FILE v1 ACCEPT {fid}"
    assert str(hr.target).startswith("#")
    fid2 = "bbccddeebbccddee"
    offer_m = f"FILE v1 OFFER tm_console bob-mh {fid2} 12 {h} M secret.txt"
    hr2 = core.handle_raw(_priv("bob-mh", "#tm", offer_m))
    assert hr2 and hr2.reply == f"FILE v1 REFUSE {fid2} :tier"


def test_fr7131_channel_file_never_shell(tmp_path):
    core = _core(tmp_path)
    hr = core.handle_raw(_priv("stranger", "#tm", "FILE v1 OFFER tm_console stranger aabbccddaabbccdd 1 " + ("b" * 64) + " S x.bin"))
    assert hr and hr.action == "seal_file"
    silent = core.handle_raw(_priv("stranger", "#tm", "whoami"))
    assert silent and silent.action == "silent_channel"


def test_fr7131_seal_airc_file_lands_in_complete(tmp_path):
    core = _core(tmp_path)
    recip = sf.ensure_identity(tmp_path)
    sender_path = tmp_path / "sender-ident.json"
    sender = seal.genkey(sender_path)
    core.handle_raw(_priv("bob-mh", "#tm", f"AGPK v1 {sender['pk']}"))
    payload = b"tabula-secret-bytes"
    env = filexfer.encode_airc_file("cred.bin", payload)
    fid = "ccddeeffccddeeff"
    blob = seal.seal_bytes_v2(env, recip["pk"], sender, "#tm", "tm_console", "bob-mh", fid)
    h = hashlib.sha256(payload).hexdigest()
    offer = f"FILE v1 OFFER tm_console bob-mh {fid} {len(payload)} {h} S cred.bin"
    assert core.handle_raw(_priv("bob-mh", "#tm", offer)).reply.endswith(fid)
    for line in seal.irc_lines_v2(blob, "tm_console", "bob-mh", fid):
        hr = core.handle_raw(_priv("bob-mh", "#tm", line))
        assert hr and hr.action == "seal_file"
    dest = tmp_path / "files" / "complete" / f"{fid}-cred.bin"
    assert dest.is_file()
    assert dest.read_bytes() == payload


def test_fr7131_basename_jail_does_not_write(tmp_path):
    core = _core(tmp_path)
    recip = sf.ensure_identity(tmp_path)
    sender = seal.genkey(tmp_path / "sender-ident.json")
    core.handle_raw(_priv("bob-mh", "#tm", f"AGPK v1 {sender['pk']}"))
    # Bypass encode_airc_file jail to simulate a hostile envelope.
    body = b"AIRC-FILE v1\nname: ..evil.txt\nbytes: 1\nsha256: " + hashlib.sha256(b"x").hexdigest().encode() + b"\nmode: 0644\n\nx"
    fid = "ddeeff00ddeeff00"
    blob = seal.seal_bytes_v2(body, recip["pk"], sender, "#tm", "tm_console", "bob-mh", fid)
    h = hashlib.sha256(b"x").hexdigest()
    core.handle_raw(_priv("bob-mh", "#tm", f"FILE v1 OFFER tm_console bob-mh {fid} 1 {h} S evil.txt"))
    for line in seal.irc_lines_v2(blob, "tm_console", "bob-mh", fid):
        core.handle_raw(_priv("bob-mh", "#tm", line))
    complete = tmp_path / "files" / "complete"
    if complete.exists():
        assert list(complete.iterdir()) == []


def test_fr7131_build_airc_hidden_imports():
    text = BUILD.read_text(encoding="utf-8")
    for mod in ("airc_seal_file", "seal", "filexfer", "protect", "wire"):
        assert f"'{mod}'" in text or f'"{mod}"' in text, mod


def test_fr7131_on_line_sends_accept_to_channel():
    src = (ROOT / "airc" / "scripts" / "airc_console_service.py").read_text(encoding="utf-8")
    assert 'hr.action == "seal_file"' in src or "action == 'seal_file'" in src
    assert "AGPK" in src
