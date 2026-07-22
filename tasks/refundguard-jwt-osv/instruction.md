Refund authorization has been bypassed in the payments service under `/app`. Fix the Express TypeScript implementation so `/app/bin/refundguard serve` verifies refund bearer tokens as described in `/app/docs/refund-security-contract.md`, without trusting attacker-controlled JWT metadata.

Also implement `/app/bin/refundguard analyze --ledger <csv> --lockfile <package-lock.json> --database <sqlite> --report <json>`. It must load the refund ledger into SQLite, identify suspicious signing patterns with SQL, query OSV for the locked npm packages, and write the deterministic report defined by the contract. The OSV endpoint is configurable for incident-response mirrors; use the documented default when it is not configured.

Work in the provided project, handle arbitrary conforming inputs rather than only the sample data, and rebuild `/app/bin/refundguard` from the TypeScript sources.
