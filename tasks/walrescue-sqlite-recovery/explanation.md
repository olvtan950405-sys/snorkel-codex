# Task Explanation — Recover a durable SQLite snapshot from a damaged WAL

_Category: Data Processing. Reviewer-facing; the agent sees the concise instruction and `/app/docs/recovery-contract.md`._

## Difficulty Explanation

`walrescue` is a crash-recovery utility for cases where an operator has a checkpointed SQLite database and a detached WAL but cannot safely ask SQLite to open the pair in place. The shipped command appears to succeed, yet merely copies the stale base database and emits an empty report. Repair requires binary-protocol work across two byte orders, a stateful two-word rolling checksum, salt and frame validation, transaction buffering, last-commit selection, repeated page replacement, database growth and truncation, and byte-canonical evidence. Several details compound: structural words remain big-endian while checksum input order changes with the magic; a checksum-valid tail is not necessarily committed; and a corrupt frame terminates the usable prefix rather than merely being skipped.

## Solution Explanation

Validate the database and 32-byte WAL headers, decode the page size, choose checksum word order from the WAL magic, and verify the header checksum. Walk fixed-size frame slots while carrying the checksum pair. Reject the first bad salt, page number, checksum, or commit size. Frames are buffered per transaction and copied into a working image only at a valid nonzero commit marker; the working image is resized to the commit's declared page count, so committed transactions can both grow and shrink it. Preserve a copy at each commit, discard the uncommitted tail, clear SQLite's two WAL-mode header bytes, hash the final bytes, and atomically write the database and ordered compact JSON report.

## Verification Explanation

The verifier is black-box and does not reuse `/app/data`. Each run creates fresh SQLite databases containing randomized records, captures multiple independent snapshots, and constructs WAL frames with an independent Python implementation. Cases cover both checksum byte orders, multiple commits that rewrite the same pages, a valid uncommitted tail, partial trailing bytes, checksum/salt/page-number failures, commit-time truncation, 1 KiB and 4 KiB pages, malformed headers, absence of a valid commit, input immutability, exact output bytes, SQLite integrity, and canonical report serialization. Randomized content, salts, frame counts, page layouts, and output digests prevent fixture-specific hardcoding. The seeded implementation fails essentially all behavioral checks; the oracle is expected to pass them all.
