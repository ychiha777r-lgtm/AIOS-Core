# README for rotation feature

This PR adds a ConnectionManager that performs secret rotation polling from a SecretStore (Vault by default) and safely reloads providers when the secret changes.

Key files:
- src/rotation_config.py
- src/ai_provider.py
- src/connection_manager.py
- src/vault_secret_store.py

How it works:
1. ConnectionManager starts a background task polling the SecretStore every `poll_interval` ± `jitter` seconds.
2. When the secret value changes, ConnectionManager attempts to call `provider.reload()` with a timeout. On failure, the old secret is retained.
3. Prometheus metrics are emitted for success/failure/duration.

Testing:
Run `pytest tests/test_connection_manager.py`.

Integration:
1. Create a RotationConfig using env vars or config file.
2. Instantiate VaultSecretStore with your Vault client.
3. Instantiate your OpenAIProvider (should implement `start`, `stop`, optionally `reload`).
4. Instantiate ConnectionManager(provider, secret_store, config) and call `start()` on app startup.
