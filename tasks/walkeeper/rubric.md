Agent inspects the recovery contract and input schemas before changing policy logic, +1
Agent converts WAL names and LSNs into numeric byte positions with the configured segment size, +3
Agent validates timeline ancestry and applies child switches at the exact boundary, +5
Agent walks the half-open recovery interval and requires the correct timeline-specific segment at every position, +5
Agent distinguishes missing WAL from present but structurally invalid WAL using the required precedence, +3
Agent implements target, timestamp, and identifier selection tie-breakers exactly, +3
Agent closes retention over every kept recoverable backup and preserves valid future WAL, +5
Agent verifies behavior with multiple inventories or focused boundary cases, +2
Agent keeps output canonical, deterministic, and data-driven, +2
Agent hard-codes shipped backup identifiers, segment names, hashes, or expected verdicts, -5
Agent treats sibling-timeline WAL as interchangeable or ignores timeline history, -5
Agent deletes WAL needed by a retained recoverable backup, -5
Agent repeatedly runs the same failing command without inspecting the failure, -1
