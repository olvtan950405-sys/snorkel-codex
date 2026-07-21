# Task Explanation — Repair PostgreSQL WAL recovery and retention planning

## Difficulty Explanation

`walkeeper` decides whether base backups can really reach their declared recovery targets and which artifacts a retention job may erase. Its shipped output is plausible but unsafe: it treats WAL names lexically, ignores timeline ancestry, accepts partial records, and protects neither full restore chains nor future WAL. A correct repair must combine PostgreSQL WAL arithmetic, half-open LSN ranges, timeline-history switches, structural validation, reason precedence, deterministic selection, and retention closure. These rules compound, so a partial implementation can select an apparently recent backup while silently deleting an ancestor segment needed to restore it.

## Solution Explanation

The oracle parses WAL names and LSNs into integer byte positions, validates each history chain to timeline 1, and determines the active ancestor or child timeline at every required segment position. It checks the backup declaration before walking `[start_lsn,target_lsn)`, distinguishes absent from malformed WAL, and records only a complete ordered chain. It then selects by target, time, and identifier; forms the policy keep-set; closes that set over every recoverable chain; and preserves valid future WAL beyond the greatest retained target. Output is recursively key-sorted compact JSON with one newline.

## Verification Explanation

The verifier runs only the public CLI against inventories created outside the image. Targeted cases cover exact timeline and segment boundaries, sibling forks, invalid histories, partial/corrupt/malformed segments, reason precedence, start-WAL mismatch, reverse targets, all selection tie-breakers, protected unrecoverable backups, minimum retention, chain closure, future WAL, canonical bytes, repeatability, and semantic changes. Expected values are derived independently in the tests rather than imported from the implementation. The shipped program fails the core recovery and retention cases while the oracle passes them.
