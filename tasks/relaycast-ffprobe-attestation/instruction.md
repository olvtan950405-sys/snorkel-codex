RelayCast's topology evidence under `/app` can no longer be trusted. Repair the Go service and reproduction pipeline so local MPEG-TS relay captures are probed and cryptographically bound to their GraphML edges.

The finished service must expose `POST /v1/probe` and `POST /v1/attest`, and `/app/bin/relaycast reproduce` must produce the same deterministic provenance report without requiring a running server. The exact request schemas, path restrictions, FFprobe normalization rules, Ed25519 message, Merkle construction, error behavior, and report format are specified in `/app/docs/attestation-contract.md`.

Implement the general contract rather than matching only the supplied incident fixture. Keep the service runnable through `/app/bin/relaycast`, and make `make reproduce` rebuild it and write the report for the paths configured by the documented environment variables. No network access is available at runtime.
