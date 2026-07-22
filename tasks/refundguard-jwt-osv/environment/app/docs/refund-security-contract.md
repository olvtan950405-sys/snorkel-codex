# Refund security contract

## Refund tokens

`POST /refunds` requires an exact `Authorization: Bearer <token>` value. Tokens are compact JWTs signed with the UTF-8 bytes in `REFUND_JWT_KEY`. Verification must require `HS256`; reject `none`, every other algorithm, malformed tokens, invalid signatures, and tokens missing any required claim. Required claims are nonempty string `sub` and `merchant`, string `scope` containing the whitespace-delimited item `refund:write`, integer `iat`, and integer `exp`. The issuer must equal `payments-api` and the audience must include `refunds`. Normal JWT time validation applies, with no clock tolerance. Do not use unverified header or payload values to choose a key or algorithm. Authentication failures return HTTP 401 and no decoded claims.

## Analysis command

The ledger is UTF-8 CSV with exactly this header:

`event_id,created_at,merchant,amount_cents,token_kid,token_alg,token_signature`

Fields may be quoted according to RFC 4180. Each data row must have a unique nonempty `event_id`, an RFC 3339 `created_at`, nonempty `merchant`, integer `amount_cents` greater than zero, nonempty `token_kid`, nonempty `token_alg`, and nonempty `token_signature`. Invalid input makes the command fail without replacing an existing database or report.

Create the requested SQLite database atomically. It must contain a `refund_events` table with columns matching the CSV header; `event_id` is its primary key and `amount_cents` is INTEGER. Identify suspicious signing groups using a SQL aggregation over that table. A group is suspicious when rows share `(token_kid, token_signature)` across more than one distinct merchant, or when `token_alg` (case-insensitive) is `none`. Emit one group for each distinct `(token_kid, token_alg, token_signature)`, ordered by `token_kid`, lower-case algorithm, then signature. Each group has exactly `token_kid`, `token_alg` (lower case), `token_signature`, `event_count`, and `merchants` (distinct names sorted lexicographically).

Read the root package and every entry in `packages` from npm lockfile version 2 or 3. Query only entries having both a nonempty `name` and `version`, de-duplicate by `(name, version)`, and order queries by name then version. POST JSON `{"package":{"ecosystem":"npm","name":NAME},"version":VERSION}` to `OSV_API_URL`, whose default is `https://api.osv.dev/v1/query`. A non-2xx response, timeout, invalid response, or unreachable service fails the command without replacing old outputs. For each returned vulnerability, emit exactly `id`, `package`, `version`, and `summary` (empty string when absent). De-duplicate by `(id, package, version)` and order by ID, package, version.

The UTF-8 report is pretty-printed JSON with a trailing newline and exactly these top-level keys: `ledger_rows` (integer), `suspicious` (array), and `vulnerabilities` (array). Output replacement must be atomic and repeated runs over identical inputs and OSV responses must be byte-identical.
