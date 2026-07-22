# Export guard contracts

`export-guard --export FILE` reads configuration from `/app/config/worker.json`. `EXPORT_GUARD_CONFIG`, `POLICY_REMOTE`, `AUDIT_DB`, and `SOURCE_REPO` may override the config path, remote, database, and source checkout (default `/app`). The config contains `policyRef`, which must name one exact `refs/tags/vMAJOR.MINOR.PATCH` release, `policyCommit`, which must be the tag's 40-character commit ID, and a safe relative `policySubmodule` path. The source checkout's `HEAD` tree must contain that path as a gitlink at `policyCommit`. Lightweight and annotated tags are valid, but a tag that does not peel to a commit is not.

An export is UTF-8 JSON with exactly `dashboardId` (a positive integer), `requestedBy` (a non-empty string), and `charts` (a non-empty array). Each chart has exactly `id` (positive integer), `thumbnail` (safe relative POSIX path), `oid` (64 lowercase hex characters), and `size` (a non-negative safe integer). Duplicate chart IDs or paths are invalid.

At the pinned commit, `policy.json` has `version: 1` and a `dashboards` object mapping decimal dashboard IDs to sorted, unique arrays of chart IDs. Every thumbnail path must be a canonical Git LFS v1 pointer in that commit, and its OID and size must equal the export before the corresponding LFS object is fetched and hashed.

The DuckDB database contains `export_audit(dashboard_id BIGINT, actor VARCHAR, decision VARCHAR, occurred_at TIMESTAMP)`. The latest row by `occurred_at` for the dashboard and actor must have decision `allow`; absence or a latest `deny` rejects the export.

Stdout is exactly one compact JSON object plus LF. Success is `{"charts":N,"dashboardId":D,"policyCommit":"...","status":"approved"}`. Failure is `{"reasons":[...],"status":"rejected"}` with unique reasons sorted lexicographically and exit status 1. Reasons are `INVALID_EXPORT`, `AUDIT_DENIED`, `POLICY_REF_INVALID`, `POLICY_PIN_MISMATCH`, `POLICY_INVALID`, `CHART_NOT_ALLOWED`, `LFS_POINTER_INVALID`, and `THUMBNAIL_MISMATCH`. Operational failures map to the closest reason and must not print tool diagnostics to stdout.
