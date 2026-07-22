# RepoGuard repository contract

This document defines RepoGuard's supported TUF profile. It is intentionally narrower than the
general TUF specification. All paths are configurable; defaults are shown below.

## Invocation and locations

`/app/bin/repoguard reconcile` performs one non-interactive reconciliation. It uses:

| Variable | Default |
|---|---|
| `REPOGUARD_REPOSITORY` | `/app/repository` |
| `REPOGUARD_TRUSTED_ROOT` | `/app/state/trusted-root.json` |
| `REPOGUARD_STATE_DB` | `/app/state/trust.db` |
| `REPOGUARD_OUT` | `/app/out` |

The repository contains `policy.json`, `metadata/*.json`, and `targets/**`. The policy's
`evaluation_time` is an RFC 3339 UTC instant. Metadata expiration is exclusive: metadata is
expired when `expires <= evaluation_time`.

## Signed metadata

Every metadata file is a JSON envelope with exactly the meaningful members `signed` and
`signatures`. A signature entry has `keyid` and a lowercase hexadecimal Ed25519 signature.
The signed bytes are the UTF-8 encoding of `signed` as compact JSON with object keys sorted
recursively, no insignificant whitespace, and no trailing newline. A threshold counts distinct
authorized key IDs with valid signatures. Duplicate signatures by one key count once; unknown
keys and invalid signatures do not count.

Keys have `keytype: ed25519`, `scheme: ed25519`, and a 32-byte lowercase-hex `public` value.
Each role has `keyids` and a positive integer `threshold` not exceeding the number of distinct
key IDs.

## Validation order

Validation is fail-closed in this order:

1. Parse the trusted and candidate roots. A rotation candidate has version exactly trusted version
   plus one and must meet the old root threshold using the old root's keys and the new root
   threshold using its own keys. If both roots have the same version, their stored bytes must be
   identical and the root must meet its own threshold; this is the idempotent no-rotation case.
   Any other version relationship is rejected. Validate the candidate root's shape and expiry.
2. Authenticate timestamp, snapshot, and top-level targets with the candidate root roles. Check
   their `_type`, expiration, and positive integer versions.
3. For every metadata role, reject a version lower than the value in SQLite table
   `accepted(role TEXT PRIMARY KEY, version INTEGER NOT NULL)`. Equality is valid and makes
   reconciliation idempotent.
4. Check every parent descriptor. A descriptor's `version`, byte `length`, and lowercase SHA-256
   must all match the referenced metadata file as stored, including its final newline. Timestamp
   commits to `snapshot.json`; snapshot commits to `targets.json` and every delegated metadata
   file that is used.
5. Authenticate each delegated envelope against the key and threshold named by its delegation in
   top-level targets, then check type, expiration, version, rollback state, and snapshot descriptor.
6. Resolve every regular file below `targets/` and every target descriptor, then verify target
   length and SHA-256.
7. Only after all metadata validation completes, atomically advance all authenticated roles in
   `accepted` and replace the trusted-root file with the candidate root. A target mismatch is a
   target verdict, not a global metadata failure, so it does not prevent a valid metadata chain
   from advancing. Any global validation failure leaves both state stores byte-for-byte unchanged.

On a global validation failure RepoGuard exits 2, writes only canonical `report.json` containing
`{"reason":<stable_reason>,"repository_status":"invalid","targets":[]}`, and does not retain stale
artifacts. It also writes exactly `repoguard: <stable_reason>` followed by one newline to stderr.
Success exits 0.

The following scored failures have fixed reason strings:

| Failure | `<stable_reason>` |
|---|---|
| A one-version root rotation does not meet the trusted old root's signature threshold | `old_root_threshold` |
| A metadata version is lower than its persisted version | `rollback:<role>` |

`<role>` is the role name used by the `accepted` table. For example, a snapshot at version 12
when `accepted('snapshot')` is 32 must produce `rollback:snapshot`; its stderr is therefore exactly
`repoguard: rollback:snapshot\n`, and `report.json` carries `"reason":"rollback:snapshot"`.

## Delegation resolution

Top-level `signed.targets` wins before delegations. Otherwise consider delegated roles in listed
order. Path patterns are slash-separated: `*` matches exactly one non-empty path segment and `**`
matches one or more remaining segments. Other characters are literal.

If a path matches a role, inspect that role's authenticated targets. A present descriptor selects
the role. If absent and the role is terminating, resolution stops and the target is unclaimed. If
the role is non-terminating, continue. A terminating role therefore prevents fallback to a later,
broader role. Delegated metadata can contain a descriptor outside its role's path patterns, but
that descriptor never claims that path.

## Target verdicts

The union of physical target paths and in-scope descriptors is sorted by UTF-8 path. Paths are
relative, use `/`, and may not be absolute, contain `.`/`..` segments, or escape the targets tree.

| Situation | Status | Reason |
|---|---|---|
| Claimed file matches length and SHA-256 | `trusted` | null |
| Claimed file exists but bytes differ | `quarantined` | `target_mismatch` |
| Physical file is not claimed after delegation resolution | `quarantined` | `unclaimed_target` |
| In-scope descriptor has no physical file | `regenerate` | `target_missing` |

Each target record has exactly `length` (actual length or null), `path`, `reason`, `role` (selected
role or null), `sha256` (actual digest or null), and `status`.

## Success artifacts

RepoGuard replaces the output tree on every run and writes:

- `report.json`: canonical compact JSON plus one newline. It has `metadata_versions` (all
  authenticated roles, sorted by name), `repository_status: "trusted"`, and sorted `targets`.
- `authorizations/<encoded>.json` for each trusted target.
- `quarantine/<encoded>.json` for each quarantined target.
- `regeneration/<encoded>.json` for each missing target.
- `audit.md`, exactly: heading `# Repository reconciliation`, blank line, one bullet per target in
  report order as ``- `<path>`: <status> (<reason-or-role>)``, then a final newline.

`<encoded>` replaces each `/` in the target path with `__` and appends `.json`. Per-target files
contain the exact canonical target record plus one newline. Outputs are derived only from current
inputs and repeated runs are byte-identical.
