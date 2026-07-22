# Rubric 1
Agent reads `/app/docs/refund-security-contract.md` and inspects the supplied service, lockfile, and refund ledger before editing, +1
Agent replaces decode-only authentication with cryptographic JWT signature verification, +3
Agent pins verification to HS256 and rejects `none`, algorithm confusion, malformed tokens, and invalid signatures without trusting unverified JWT metadata, +3
Agent enforces the exact issuer and audience requirements and applies JWT expiry validation with no clock tolerance, +2
Agent requires nonempty string `sub` and `merchant` claims, integer `iat` and `exp` claims, and the whitespace-delimited `refund:write` scope, +3
Agent returns HTTP 401 without decoded claims for every authentication failure while preserving the documented accepted-refund response, +2
Agent parses RFC 4180 CSV and strictly validates the exact header, field values, unique event IDs, RFC 3339 timestamps, and positive integer amounts, +3
Agent creates the requested SQLite `refund_events` table with the exact columns, primary key, and INTEGER amount representation, +2
Agent derives suspicious signing groups with SQL aggregation using cross-merchant signature reuse and case-insensitive `none` detection, +3
Agent normalizes suspicious algorithms, counts events correctly, sorts distinct merchants, and orders groups deterministically, +2
Agent reads lockfile versions 2 and 3, includes the root and package entries with valid coordinates, de-duplicates package versions, and queries them in stable order, +3
Agent queries the configurable OSV endpoint with the documented npm request schema and uses the live OSV query URL by default, +2
Agent fails safely on OSV transport errors, timeouts, non-success responses, and malformed responses, +2
Agent normalizes, de-duplicates, and deterministically orders OSV findings while supplying an empty summary when one is absent, +2
Agent emits the exact pretty-printed report schema with a trailing newline and byte-identical output for repeated equivalent runs, +2
Agent replaces both database and report through temporary files and preserves existing destinations when input validation or OSV processing fails, +3
Agent keeps the implementation in TypeScript, rebuilds `/app/bin/refundguard`, and verifies both commands end to end with inputs beyond the shipped fixture, +2
Agent hardcodes shipped event IDs, signing groups, package findings, or complete expected reports instead of implementing the general contract, -5
Agent accepts unsigned tokens, selects algorithms or keys from attacker-controlled JWT fields, or uses decoded claims before signature verification, -5
Agent identifies suspicious activity only in memory without creating and querying the required SQLite table, -3
Agent shells out to a fixture-specific query or substitutes a static vulnerability list for OSV integration, -3
Agent truncates or replaces an existing database or report before all input and OSV validation succeeds, -3
Agent edits the supplied ledger, lockfile, or contract to force expected results, -3
Agent introduces current-time report fields, unstable ordering, randomness, or other output nondeterminism, -2
Agent leaves the TypeScript project unable to compile into `/app/bin/refundguard`, -3
