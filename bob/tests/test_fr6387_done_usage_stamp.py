"""FR #6387: worker stamps measured usage onto DONE outbox lines."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bob" / "scripts"))
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_worker as bw  # noqa: E402
import done_usage  # noqa: E402


class _FakeIrc:
    shop = "#redqueen"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def say(self, target: str, text: str) -> bool:
        self.sent.append((target, text))
        return True


def test_drain_outbox_enriches_done_with_grok_fixture(tmp_path: Path, monkeypatch):
    usage = {
        "session": {
            "inputTokens": 42,
            "outputTokens": 7,
            "cachedReadTokens": 11,
            "primaryModelId": "grok-4.5-build",
        }
    }
    usage_path = tmp_path / "usage.json"
    usage_path.write_text(json.dumps(usage), encoding="utf-8")
    monkeypatch.setenv("BOB_GROK_USAGE_PATH", str(usage_path))

    class _Sup:
        kind = "grok"
        cwd = str(tmp_path)
        sessions = ["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]
        sessions_root = tmp_path
        run_dir = tmp_path

        def measure_done_usage(self):
            return done_usage.measure_seat_usage(
                "grok", grok_usage_path=usage_path
            )

        def enrich_done_line(self, payload: str) -> str:
            return done_usage.enrich_done_payload(payload, self.measure_done_usage())

    outbox = tmp_path / "outbox.txt"
    outbox.write_text(
        "PRIVMSG #redqueen :DONE FR o/r#1 https://github.com/o/r/pull/1\n",
        encoding="utf-8",
    )
    irc = _FakeIrc()
    logs: list[str] = []
    n = bw.drain_outbox(
        outbox,
        irc,
        logs.append,
        enrich_line=_Sup().enrich_done_line,
    )
    assert n == 1
    assert len(irc.sent) == 1
    _tgt, text = irc.sent[0]
    assert "DONE FR o/r#1" in text
    assert "model=xai/grok-4.5-build" in text
    assert "tokens_in=42" in text
    assert "tokens_out=7" in text
    assert "tokens_cached=11" in text


@pytest.mark.parametrize(
    "kind,filename,doc,model_sub,tin,tout,tc",
    [
        (
            "cursor",
            "cursor-usage.json",
            {
                "model": "cursor/composer-1",
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 1,
                    "cache_read_tokens": 2,
                },
            },
            "cursor/composer-1",
            5,
            1,
            2,
        ),
        (
            "opencode",
            "opencode-usage.json",
            {
                "model": "opencode/glm-5.3",
                "tokens": {"input": 8, "output": 3, "cache": 1},
            },
            "opencode/glm-5.3",
            8,
            3,
            1,
        ),
        (
            "aider",
            "aider-usage.json",
            {
                "model": "aider/deepseek-chat",
                "prompt_tokens": 9,
                "completion_tokens": 4,
                "cached_tokens": 0,
            },
            "aider/deepseek-chat",
            9,
            4,
            0,
        ),
    ],
)
def test_drain_outbox_enriches_per_agent(
    tmp_path: Path, kind, filename, doc, model_sub, tin, tout, tc
):
    path = tmp_path / filename
    path.write_text(json.dumps(doc), encoding="utf-8")
    usage = done_usage.measure_seat_usage(
        kind,
        cursor_usage_path=path if kind == "cursor" else None,
        opencode_usage_path=path if kind == "opencode" else None,
        aider_usage_path=path if kind == "aider" else None,
    )
    outbox = tmp_path / "outbox.txt"
    outbox.write_text(
        "DONE MRB o/r#2 PASS https://github.com/o/r/pull/2\n",
        encoding="utf-8",
    )
    irc = _FakeIrc()
    n = bw.drain_outbox(
        outbox,
        irc,
        lambda _m: None,
        enrich_line=lambda p: done_usage.enrich_done_payload(p, usage),
    )
    assert n == 1
    text = irc.sent[0][1]
    assert model_sub in text
    assert f"tokens_in={tin}" in text
    assert f"tokens_out={tout}" in text
    assert f"tokens_cached={tc}" in text


def test_drain_outbox_unknown_when_no_usage(tmp_path: Path):
    outbox = tmp_path / "outbox.txt"
    outbox.write_text(
        "DONE UAT o/r#main PASS https://github.com/o/r/releases/tag/v1\n",
        encoding="utf-8",
    )
    irc = _FakeIrc()
    n = bw.drain_outbox(
        outbox,
        irc,
        lambda _m: None,
        enrich_line=lambda p: done_usage.enrich_done_payload(
            p, done_usage.measure_seat_usage("grok", grok_usage_path=tmp_path / "missing.json")
        ),
    )
    assert n == 1
    text = irc.sent[0][1]
    assert "tokens=unknown" in text
    assert "tokens_in=" not in text
