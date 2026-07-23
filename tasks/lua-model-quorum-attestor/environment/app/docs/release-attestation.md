# Release attestation contract

`GET /healthz` returns status 200, media type `application/json`, and `{"status":"ok"}` followed by one LF. `POST /attest-release` reads the release lock selected at startup by `RELEASE_LOCK_PATH` (default `/app/release.lock`), public keys from `MAINTAINER_KEY_DIR` (default `/app/config/maintainers`), and bare mirrors below `MODEL_MIRROR_ROOT` (default `/srv/model-mirrors`). Inputs must not be modified.

The lock is UTF-8, LF-terminated, and has no blank or unknown records. Its exact form is:

```text
release-lock 1
release <ASCII release id>
quorum <integer>
model <model id> <mirror name> <tag> <40-hex commit> <artifact path> <64-hex sha256> <size>
model ...
signer <key id> <base64 RSA signature>
signer ...
```

Release ids, mirror names, tags, and key ids use ASCII letters, digits, `.`, `_`, and `-`; model ids contain at least one slash and use those characters in every nonempty component. Artifact paths are relative POSIX paths with nonempty components from the same character set and no `.` or `..`. Digests and commits are lowercase hexadecimal. Sizes are canonical decimal integers from 0 through 1,000,000,000. Quorum is canonical decimal from 1 through 20. There are one or more unique model ids in bytewise order followed by one or more unique signer ids in bytewise order. Lines beginning `<<<<<<<` or `>>>>>>>`, or equal to `=======`, yield `LOCK_CONFLICT`; every other grammar failure yields `INVALID_LOCK`.

Each signature is RSA-SHA256 over the exact bytes preceding the first `signer` line, including its preceding LF. A signer is valid only when `<key-dir>/<key-id>.pem` is a regular public-key file and `openssl` verifies its signature. At least `quorum` distinct signatures must be valid or the result includes `QUORUM_NOT_MET`; invalid and unknown signatures do not count.

For every model, `<mirror-root>/<mirror-name>.git` is the bare remote. The named tag must be an annotated tag object, and peeling it must produce exactly the locked commit; otherwise include `TAG_BINDING_INVALID`. In a fresh temporary clone, inspect the artifact at that commit before smudging: it must be an exact Git LFS v1 pointer whose oid and size equal the lock, or include `LFS_POINTER_INVALID`. An implementation may stop checking that model after this pointer failure. When the pointer is valid, materialize the LFS object, then compare its regular-file size and `sha256sum` digest with the lock; include `ARTIFACT_SIZE_MISMATCH` and/or `ARTIFACT_DIGEST_MISMATCH` as applicable. Collect unique reasons across models and return status 422 with compact, recursively key-sorted `{"reasons":[...],"status":"rejected"}` plus LF, with reasons sorted.

On success, form one evidence line per model as `<model-id> <commit> <artifact-path> <digest> <size>\n` in model order. Compute the lowercase SHA-256 of their concatenation with `sha256sum`. Return status 200 and compact key-sorted JSON plus LF containing exactly `evidence_sha256`, `models` (an integer equal to the number of model records), `release`, `signers` (an array containing only the sorted ids of valid signers), and `status`=`accepted`.

All subprocess-derived values are untrusted operands. They must not become shell syntax or options. Remove temporary state after success or rejection.
