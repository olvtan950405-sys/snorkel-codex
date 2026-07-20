# walrescue recovery contract

`walrescue recover` reconstructs a standalone SQLite database from a checkpointed database file and its WAL. It parses the WAL itself; spawning `sqlite3`, opening the pair through a SQLite library, or copying/renaming the WAL beside the output is not recovery under this contract.

## Supported inputs

The base file is an ordinary SQLite 3 database. Its 16-byte magic must be `SQLite format 3\0`. WAL files use SQLite WAL format version `3007000`, a page size from 512 through 65536 that is a power of two, and magic `0x377f0682` or `0x377f0683`. In the WAL header, a page-size field of `1` means 65536. Integers other than checksum words are big-endian.

The two magic values select the byte order in which checksum input words are read:

- `0x377f0682`: little-endian checksum words
- `0x377f0683`: big-endian checksum words

The base database page size in bytes 16–17 (`1` means 65536) must equal the WAL page size. A base file whose length is not an exact number of pages is invalid.

## Rolling checksum

A checksum is a pair `(s0, s1)` of unsigned 32-bit words with wraparound arithmetic. For each adjacent pair of 32-bit input words `(x0, x1)`:

```
s0 = s0 + x0 + s1
s1 = s1 + x1 + s0
```

The WAL header checksum starts at `(0, 0)` and consumes the first 24 bytes of the 32-byte header. Header words are interpreted in the checksum byte order selected by the magic. The resulting pair must equal the two big-endian checksum values stored at header offsets 24 and 28.

Frames begin at offset 32 and have a 24-byte header followed by exactly one database page. A frame checksum continues from the preceding valid checksum state and consumes the first 8 bytes of its frame header followed by its page data. It does not consume salts or stored checksum words. Its resulting pair must equal the big-endian values at frame-header offsets 16 and 20.

## Frames and transactions

The frame-header fields are:

| Offset | Size | Meaning |
|---|---:|---|
| 0 | 4 | database page number, starting at 1 |
| 4 | 4 | database size in pages after commit, or zero |
| 8 | 4 | salt 1 |
| 12 | 4 | salt 2 |
| 16 | 4 | checksum word 1 |
| 20 | 4 | checksum word 2 |

Every valid frame must repeat both salts from the WAL header and have a nonzero page number. A zero database-size field means the transaction continues. A nonzero database-size field commits every valid frame since the preceding commit, including the commit frame. That size must be nonzero, must not be smaller than the commit frame's page number, and no frame in that transaction may address a page beyond it.

Frames from incomplete transactions are never applied. When a later transaction writes a page already written by an earlier committed transaction, the later committed image wins. A commit database size may shrink the database; pages at larger numbers are discarded even if an earlier transaction committed them.

## Stopping rules

Scan complete frame slots in order. Stop before the first frame with a bad salt, zero page number, invalid checksum, or invalid commit size. Also stop when the file ends with bytes insufficient for a complete frame. Once scanning stops, nothing later in the file is considered, even if it resembles a valid frame.

Valid frames after the last commit form an uncommitted tail and are ignored. A malformed WAL header, unsupported format, mismatched page size, malformed base database, or a WAL with no valid commit is a fatal error: return nonzero and do not leave an output database or report behind.

## Output database

Start from the bytes of the base database. Apply committed frames in transaction order at `(page_number - 1) * page_size`, extending with zero-filled pages when necessary. After each commit, resize the working database to exactly the committed database size. The final file is therefore exactly `database_pages * page_size` bytes.

The recovered database must be standalone. Clear the WAL-mode remnants in page 1 by setting bytes 18 and 19 (the file read/write versions) to `1`. Do not change any other byte unless supplied by a committed page image or removed by commit-time truncation.

Write the database atomically: create a temporary file in the output directory, fsync it, rename it over the requested output, then fsync the directory. The input database and WAL must never be modified.

## Canonical report

On success, write one compact JSON object followed by one newline. Keys must appear in this exact order:

```
status, page_size, frames_scanned, valid_frames, committed_frames,
transactions, database_pages, ignored_tail_frames, stop_reason, output_sha256
```

Values have these meanings:

- `status`: always `"recovered"`
- `page_size`: decoded WAL page size
- `frames_scanned`: complete frame slots examined, including the first rejected slot
- `valid_frames`: checksum/salt-valid frames before the stopping point, including an uncommitted tail
- `committed_frames`: valid frames through the last valid commit
- `transactions`: valid commits through that point
- `database_pages`: size named by the last valid commit
- `ignored_tail_frames`: `valid_frames - committed_frames`
- `stop_reason`: `"end_of_wal"`, `"partial_frame"`, `"salt_mismatch"`, `"zero_page_number"`, `"checksum_mismatch"`, or `"invalid_commit_size"`
- `output_sha256`: lowercase SHA-256 hex digest of the final database bytes

If the scan reaches the exact end of the WAL, use `end_of_wal`. If trailing bytes remain but cannot form a frame, use `partial_frame`. A rejected complete frame is included in `frames_scanned` but not `valid_frames`.
