"""FR #6553: CI freeze host must install PyYAML so assert_jeeves_yaml_embed can pass.

FR #6487 added --hidden-import yaml / --collect-all yaml and requirements-freeze.txt,
but Install-BobiversePythonDeps only installed cryptography. build-jeeves then froze
without yaml and failed assert_jeeves_yaml_embed (PYZ missing ['yaml']).
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / '.github' / 'workflows' / 'build-jeeves.yml'
EAR_WF = ROOT / '.github' / 'workflows' / 'build-bob-ear.yml'
COMMON = ROOT / 'common' / 'scripts' / 'Bobiverse-Common.ps1'
BUILD = ROOT / 'jeeves' / 'scripts' / 'Build-Jeeves.ps1'
REQ = ROOT / 'common' / 'requirements-freeze.txt'


def test_fr6553_install_python_deps_includes_pyyaml_or_freeze():
    text = COMMON.read_text(encoding='utf-8')
    assert 'function Install-BobiversePythonDeps' in text
    # Must install freeze file and/or explicit pyyaml so collect-all yaml works on CI.
    assert 'requirements-freeze.txt' in text
    assert 'PyYAML' in text or 'pyyaml' in text.lower()
    assert 'cryptography' in text  # keep prior dep


def test_fr6553_build_jeeves_workflow_installs_freeze_deps():
    text = WF.read_text(encoding='utf-8')
    assert 'Install-BobiversePythonDeps' in text
    # Workflow path filter must include freeze requirements so dep-only PRs rebuild.
    assert 'requirements-freeze.txt' in text or 'common/requirements-freeze.txt' in text
    assert REQ.is_file()
    assert 'PyYAML' in REQ.read_text(encoding='utf-8')


def test_fr6553_build_jeeves_preflight_import_yaml():
    build = BUILD.read_text(encoding='utf-8')
    assert 'import yaml' in build
    assert '6553' in build or '6487' in build
    assert 'assert_jeeves_yaml_embed' in build


def test_fr6553_bob_ear_workflow_still_installs_python_deps():
    text = EAR_WF.read_text(encoding='utf-8')
    assert 'Install-BobiversePythonDeps' in text


def test_fr6553_build_bob_ear_preflight_import_yaml():
    ear = (ROOT / 'bob' / 'scripts' / 'Build-BobEar.ps1').read_text(encoding='utf-8')
    assert 'import yaml' in ear
    assert '6553' in ear or '6487' in ear
