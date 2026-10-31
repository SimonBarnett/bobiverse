# Airc Priority worker (in-service)

FR #5283. This folder is the **service-owned** Priority Web SDK worker layout.

- Path: `<ai root>\airc\airc\priority-worker\` after pack (next to `airc.exe`)
- Invoke only from the Airc Priority module (`AIRC_PRIORITY_OWNED=1` or `--from-airc`)
- No `PriorityClient.exe` and no agent `drop\` one-off clients
- Node `priority-web-sdk` vendor files land here in a later pack step; this slice ships the owned entry + pack/MSI path
