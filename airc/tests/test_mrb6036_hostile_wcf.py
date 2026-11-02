"""Hostile pins for PR #6036 / FR #6035: no IRC allowlist bypass, no CredMan echo."""
from __future__ import annotations

import priority_wcf as wcf


def _secret() -> str:
    return "FAKE_" + "WCF" + "ECHO" + "77"


class _Allow:
    def get(self, ident):
        if ident == "example-dev":
            return type(
                "I",
                (),
                {
                    "public_dict": lambda self: {
                        "url": "https://priority.example.invalid",
                        "user": "api-user",
                        "credentialTarget": "PriorityWeb/example-dev",
                    }
                },
            )()
        return None


def test_mrb6036_allowlist_ignores_irc_url_override():
    seen = []

    def fake_post(url, data, headers, timeout_s=30.0):
        seen.append(url)
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>ok</s:Body></s:Envelope>'
        )

    out = wcf.run_priority_wcf(
        "PRIORITY wcf GetVersion url=https://evil.example.invalid user=x",
        allowlist=_Allow(),
        passed_password=_secret(),
        http_post=fake_post,
        mode="relay",
    )
    assert not any("evil.example" in (u or "") for u in seen)
    assert out.get("ok") is False
    assert out.get("error") in (
        wcf.PRIORITY_NOT_CONFIGURED,
        "unknown-instance",
        wcf.WCF_BAD_OP,
    )


def test_mrb6036_credman_echo_redacted_from_result():
    secret = _secret()

    def fetch(_target):
        return secret

    def echo_post(url, data, headers, timeout_s=30.0):
        return 200, (
            f'<s:Envelope xmlns:s="{wcf.SOAP_NS}"><s:Body>'
            f"<GetVersionResult>pw {secret}</GetVersionResult>"
            "</s:Body></s:Envelope>"
        )

    out = wcf.PriorityWcfClient(
        {
            "url": "https://priority.example.invalid",
            "user": "api-user",
            "credentialTarget": "PriorityWeb/example-dev",
        },
        cred_fetcher=fetch,
        http_post=echo_post,
    ).get_version()
    blob = str(out)
    assert secret not in blob
    assert out.get("ok") is True
