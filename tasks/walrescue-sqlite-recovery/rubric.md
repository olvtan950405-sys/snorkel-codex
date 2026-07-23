# Rubric 1
Agent runs `walrescue` against the gateway evidence and inspects the generated artifacts, +1
Agent reads `/app/docs/recovery-contract.md` before changing trust decisions, +1
Agent inspects the SQLite database header and WAL bytes with an appropriate binary or forensic tool, +1
Agent validates the SQLite and WAL headers, format version, page sizes, and header checksum, +3
Agent handles the SQLite/WAL 65536-byte page-size sentinel consistently, +2
Agent selects checksum word byte order from the WAL magic while decoding structural integers as big-endian, +3
Agent carries both rolling checksum words from the WAL header through consecutive frames with uint32 wraparound, +3
Agent validates each frame's salts, nonzero page number, and stored checksum before accepting it, +3
Agent treats transaction frames as untrusted until a valid nonzero commit-size marker authenticates the transaction, +3
Agent preserves the last valid image when the same page appears more than once inside one committed transaction, +2
Agent stops at the first invalid or partial frame and ignores every later byte, +2
Agent excludes checksum-valid frames after the last commit from the trusted database image, +2
Agent applies later committed page images over earlier images and zero-extends the base when required, +2
Agent resizes the working database at each commit so a later commit can truncate pages, +3
Agent applies a committed page-1 image before clearing only the two WAL-mode database-header bytes, +3
Agent emits the canonical evidence report with exact counters, stop reason, key order, digest, and one newline, +3
Agent writes output files atomically without modifying either input, +2
Agent rejects output/report paths that alias inputs, alias each other, or are existing symlinks before modifying artifacts, +3
Agent rejects unexpected trailing CLI arguments and leaves no output artifacts, +2
Agent removes stale output artifacts on fatal evidence errors, +2
Agent ensures `/app/bin/walrescue` enforces the contract after the application is rebuilt, +2
Agent invokes SQLite, renames the input WAL beside the output, or delegates WAL recovery to another database library, -5
Agent hardcodes decisions, page images, counters, or report values for the shipped gateway fixture, -5
Agent applies frames before seeing their transaction's valid commit marker, -3
Agent continues scanning after a corrupt frame or checksum chain break, -3
Agent edits the shipped database or WAL to force a passing result, -3
Agent overwrites input evidence, follows output symlinks, or leaves stale artifacts after a fatal error, -5
Agent leaves the recovery gate unusable after rebuild, -2
