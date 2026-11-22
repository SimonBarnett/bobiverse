# BOB-45 Agents > Plan models webhook

Agents > Plan reads the Plan object from the models webhook file before it starts the exe.

Path: `BOB_MODELS_WEBHOOK_FILE`, or `run/models-webhook.json`.

The tray log cites `plan-models webhook model=... context=... effort=...`. A document with no Plan object does not invent settings.
