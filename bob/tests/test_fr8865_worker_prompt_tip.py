"""FR #8865: seat prompt comes from the install-root template, not frozen text."""
from __future__ import annotations

from pathlib import Path

import bob_worker


def test_fr8865_install_tip_overrides_builtin(tmp_path: Path):
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    worker = install / "worker"
    worker.mkdir()
    scripts.joinpath("worker_prompt_template.txt").write_text(
        "tip @@WORKER_DIR@@ nick=@@NICK@@ machine=@@MACHINE@@ out=@@OUTBOX@@\n",
        encoding="utf-8",
    )
    text = bob_worker.worker_prompt(str(worker), str(tmp_path / "run"), "marchhare", "marchhare-1")
    assert text.startswith("tip ")
    assert str(worker) in text
    assert "nick=marchhare-1" in text
    assert "machine=marchhare" in text
    assert text.endswith("out=" + str(tmp_path / "run" / "outbox.txt") + "\n") or (
        "out=" + str(Path(tmp_path / "run" / "outbox.txt")) in text
    )


def test_fr8865_stale_bob_bob_scripts_template_is_ignored(tmp_path: Path):
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    worker = install / "worker"
    worker.mkdir()
    scripts.joinpath("worker_prompt_template.txt").write_text(
        "bad @@WORKER_DIR@@ @@NICK@@ @@MACHINE@@ bob/bob/scripts/skill_dag_mcp.py\n",
        encoding="utf-8",
    )
    text = bob_worker.worker_prompt(str(worker), str(tmp_path / "run"), "marchhare", "marchhare-1")
    assert "bob/bob/scripts" not in text.replace("\\", "/")
    assert ".cursor" in text or "mcp.json" in text


def test_fr8865_shipped_template_has_mcp_json_not_doubled_bob_scripts():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "bob" / "scripts" / "worker_prompt_template.txt").read_text(encoding="utf-8")
    assert "@@WORKER_DIR@@" in raw
    assert "bob/bob/scripts" not in raw.replace("\\", "/")
    assert "mcp.json" in raw
