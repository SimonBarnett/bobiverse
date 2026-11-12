"""MRB #6791 hostile pins for FR #6757 HTTPS front door / XFF."""
from __future__ import annotations

import jeeves_settings as js
import jeeves_settings_http as http


def test_mrb6791_ipv6_loopback_trusts_xff():
    ip = js.effective_client_ip("::1", "10.0.0.8")
    assert js.reject_non_lan(ip) is None
    assert js.effective_client_ip("::1", "8.8.8.8")
    assert js.reject_non_lan(js.effective_client_ip("::1", "8.8.8.8"))


def test_mrb6791_lan_peer_ignores_spoofed_xff_public():
    ip = js.effective_client_ip("10.0.0.5", "8.8.8.8")
    assert ip == "10.0.0.5"
    assert js.reject_non_lan(ip) is None


def test_mrb6791_loopback_empty_xff_uses_peer():
    assert js.effective_client_ip("127.0.0.1", "") == "127.0.0.1"
    assert js.effective_client_ip("127.0.0.1", None) == "127.0.0.1"


def test_mrb6791_front_door_off_honours_explicit_bind(monkeypatch):
    monkeypatch.delenv("JEEVES_SETTINGS_FRONTDOOR", raising=False)
    monkeypatch.setenv("JEEVES_SETTINGS_HTTP_BIND", "10.0.0.5")
    assert http.resolve_bind_host() == "10.0.0.5"
