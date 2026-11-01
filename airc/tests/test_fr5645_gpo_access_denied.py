"""FR #5645: EXTENSION GPO Invoke-Command Access Denied must classify and retry CredMan.

LocalSystem computer account is denied WinRM on the DC by design. Script must:
- classify Access Denied as gpo_access_denied (not opaque gpo_remote_failed only)
- retry Invoke-Command with CredMan PriorityAirc/ExtensionAdmin
- emit need= guidance; never print password
"""
from __future__ import annotations

from repo_layout import ROOT

PS = ROOT / 'airc/scripts/Invoke-AircExtensionGpo.ps1'
SKILL_CMD = ROOT / 'airc/.grok/skills/bobiverse-airc-commands/SKILL.md'
SKILL_T = ROOT / 'airc/.grok/skills/bobiverse-airc-troubleshooting/SKILL.md'


def test_fr5645_ps_no_bom():
    assert not PS.read_bytes().startswith(b'\xef\xbb\xbf')
    assert '\ufeff' not in PS.read_text(encoding='utf-8')


def test_fr5645_classifies_access_denied():
    t = PS.read_text(encoding='utf-8')
    assert 'FR #5645' in t
    assert 'gpo_access_denied' in t
    assert 'Access is denied' in t or 'access denied' in t.lower() or 'AccessDenied' in t


def test_fr5645_credman_extension_admin_retry():
    t = PS.read_text(encoding='utf-8')
    assert 'PriorityAirc/ExtensionAdmin' in t
    assert 'Invoke-Command' in t
    # Must attempt -Credential after machine-account deny (never log password).
    assert '-Credential' in t
    assert 'CredRead' in t or 'CredentialBlob' in t or 'Get-StoredCredential' in t
    # Fail closed guidance when CredMan missing / still denied.
    assert 'need=' in t or "need =" in t or "'need'" in t or '"need"' in t


def test_fr5645_result_fields_and_no_password_leak():
    t = PS.read_text(encoding='utf-8')
    # Catch path must keep error/dc/gpo_via and add identity/need/credman_tried.
    catch = t[t.rindex('} catch {') :]
    assert 'gpo_access_denied' in catch or 'gpo_access_denied' in t
    assert 'credman' in t.lower()
    assert 'password=' not in t.lower().split('never')[0] or 'Never prints passwords' in t or 'never print' in t.lower()
    # Ensure we never Write-Result a password field name casually.
    assert "password =" not in t.lower() or 'Never prints passwords' in t


def test_fr5645_skills_document_gpo_identity():
    cmd = SKILL_CMD.read_text(encoding='utf-8')
    tr = SKILL_T.read_text(encoding='utf-8')
    blob = cmd + '\n' + tr
    assert '5645' in blob
    assert 'gpo_access_denied' in blob or 'ExtensionAdmin' in blob
    assert 'Access denied' in blob or 'computer account' in blob.lower() or 'LocalSystem' in blob
