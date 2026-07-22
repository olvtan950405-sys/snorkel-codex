# Build the Locksmith runtime audit pipeline

The Gin-based Locksmith fixture in `/app/fixture` issues JWTs, rotates signing keys, and stores encrypted leases in bbolt. Implement `/app/cmd/locksmith-audit` and build `/app/bin/locksmith-audit` so it performs the incident audit defined in `/app/docs/audit-contract.md`.

The command must start the supplied API itself, discover its actual listening port and bbolt file from the running process, replay the request fixture, verify issued JWTs against the observed JWKS (including rotation), decrypt and reconcile the resulting bbolt records, and verify every selected Go module tag against its configured Git remote before writing the deterministic report.

Treat process output, HTTP responses, JWT headers and claims, database bytes, module policy, Git refs, paths, and remote locations as untrusted. Do not use a shell to interpolate them, do not follow mutable refs, do not trust a JWT merely because it decodes, and do not modify the request fixture, module policy, remote, or final database. The pipeline must clean up its child process and temporary state on both success and failure and work with other conforming fixtures selected through the documented flags.
