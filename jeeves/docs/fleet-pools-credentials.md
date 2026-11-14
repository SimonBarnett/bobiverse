# Jeeves fleet pool credentials (FR #7255 / #7288)

Jeeves on walrus fetches Copilot and OpenCode free/Go once per minute into digest
`fleet_pools`. Credentials stay on the Jeeves service account. The digest and logs
show only a **source tag** (never the secret value).

## Credential Manager targets

Generic Windows credentials (password blob holds the secret):

| Secret | CredMan target |
|--------|----------------|
| GitHub token (Copilot) | `bobiverse/jeeves/github-token` |
| OpenCode Go API key | `bobiverse/jeeves/opencode-go-key` |

Resolve order for each secret:

1. CredMan target above (works for LocalSystem / the Jeeves service account).
2. Environment (`GH_TOKEN` / `GITHUB_TOKEN`, or `BOB_OPENCODE_GO_API_KEY`).
3. Files under the **Jeeves** install root (`JEEVES_INSTALL_ROOT` or
   `<ai root>\jeeves`): `config\github.token`, `config\opencode-go.apikey` /
   `config\opencode-keys\`. Not the ear `scripts\bob-ear.exe` install root.

Missing everything yields `no_token` / `no_key` with source `none:credman:...,env:...,file:...`.

## One-time setup on walrus (as the Jeeves service account)

Run elevated **as the same account that runs `ircJeeves`** (often LocalSystem via
`psexec -s`, or the dedicated service user):

```bat
cmdkey /generic:bobiverse/jeeves/github-token /user:token /pass:YOUR_GITHUB_TOKEN
cmdkey /generic:bobiverse/jeeves/opencode-go-key /user:opencode /pass:YOUR_OPENCODE_GO_KEY
```

PowerShell equivalent (still as that account):

```powershell
cmdkey /generic:bobiverse/jeeves/github-token /user:token /pass:$GitHubToken
cmdkey /generic:bobiverse/jeeves/opencode-go-key /user:opencode /pass:$GoKey
```

Do not echo the secret into chair logs, IRC, or the digest. After setup, wait one
fleet tick (~60s) and confirm digest `fleet_pools.*.source` shows
`credman:bobiverse/jeeves/...` with a fresh `fetched_at`.

## Related

- Code: `common/scripts/fleet_pool_fetch.py` (`resolve_fleet_github_token`,
  `resolve_fleet_opencode_go_key`).
- Pins: `common/tests/test_fr7288_fleet_credman.py`, `test_fr7255_fleet_pool_fetch.py`.
