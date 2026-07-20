# Rubric 1
Agent runs the shipped walrescue utility and inspects its failure or generated artifacts before editing, +1
Agent reads `/app/docs/recovery-contract.md` before implementing recovery, +1
Agent inspects the SQLite database header and WAL bytes with an appropriate binary tool, +1
Agent validates the SQLite and WAL headers, format version, page sizes, and header checksum, +3
Agent selects checksum word byte order from the WAL magic while decoding structural integers as big-endian, +3
Agent carries both rolling checksum words from the WAL header through consecutive frames with uint32 wraparound, +3
Agent validates each frame's salts, nonzero page number, and stored checksum before accepting it, +3
Agent buffers transaction frames and applies them only when a valid nonzero commit-size marker is reached, +3
Agent stops at the first invalid or partial frame and ignores every later byte, +2
Agent excludes checksum-valid frames after the last commit from the recovered database, +2
Agent applies later committed page images over earlier images and zero-extends the base when required, +2
Agent resizes the working database at each commit so a later commit can truncate pages, +3
Agent clears the two WAL-mode database-header bytes without altering unrelated recovered bytes, +2
Agent emits the canonical report with exact counters, stop reason, key order, digest, and one newline, +3
Agent writes output files atomically without modifying either input, +2
Agent rebuilds `/app/bin/walrescue` from the repaired Go sources and verifies it end to end, +2
Agent invokes SQLite, renames the input WAL beside the output, or delegates WAL recovery to another database library, -5
Agent hardcodes decisions, page images, counters, or report values for the shipped gateway fixture, -5
Agent applies frames before seeing their transaction's valid commit marker, -3
Agent continues scanning after a corrupt frame or checksum chain break, -3
Agent edits the shipped database or WAL to force a passing result, -3
Agent leaves Go sources that fail to format or compile, -2
