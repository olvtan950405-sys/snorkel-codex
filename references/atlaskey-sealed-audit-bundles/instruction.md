# Authenticate the sealed audit bundles again

The offline stations that sign our audit exports were upgraded to Sealer 2.0, and since then the
audit service in `/app` has not been able to authenticate a single bundle. The seal footer format
changed with that release and the vendor never updated `/app/docs/vendor/akb-format.md`, which
still documents the old one. Until the seals can be verified again nothing gets signed off — and
nothing may be signed off that we cannot verify.

Make `POST /audit-bundles/:bundleId/verify` authenticate the archives in `/app/var/bundles`:
reconstruct the current seal footer, check its MAC and open its AES-GCM payload under the keys
derived for the sealing tenant's key epoch, and hold the archive against what the seal actually
commits to. The Parquet event table has to be read through `nodejs-polars` — the seal commits to
the event rows, not to the bytes of the file. Tampered bundles, bundles sealed with a key that was
revoked or out of its epoch, and bundles we have already accepted once all have to be caught and
named.

Every trust decision — whether the tenant is onboarded and active, whether the epoch exists and the
seal names its key, whether the key was revoked before the bundle was sealed, whether the tenant is
permitted that algorithm suite, whether this seal has been seen before — has to come from the
DuckDB trust catalog and the keyring the service was started with. Staging and production point it
at their own, holding tenants that appear nowhere under `/app/data`, so the development values
currently sitting in `/app/src/catalog/trust-catalog.js` cannot stand.

`/app/docs/audit-api.md` is the contract: the verdict fields, every rejection reason, the order the
checks run in, and what an accepted seal writes back to the ledger. Keep the service startable with
`node /app/bin/atlaskey-audit.js --port <n>`.
