# Model lock verification contract

`lockguard` exposes `GET /healthz` and `POST /verify-lock`. Responses are compact JSON with a trailing newline and `application/json` content type. Health returns status 200 and `{"status":"ok"}`. Verification returns status 200 with exactly `{"artifacts":N,"commit":"<40 lowercase hex>","status":"accepted"}` on success. A rejected request returns status 422 with exactly `{"reasons":[...],"status":"rejected"}`; reasons are unique and lexicographically sorted.

The service reads the lock selected by `MODEL_LOCK_PATH` (default `/app/deps.lock`), the PEM public key selected by `MAINTAINER_KEY_PATH` (default `/app/config/maintainer-public.pem`), and the local remote selected by `MODEL_REMOTE` (default `/srv/model-remotes/sentence-transformers/all-MiniLM-L6-v2.git`). These settings are fixed at startup. Verification is offline and must not alter any of those inputs.

## Lock format

The UTF-8 lock is line oriented. It must contain these records in this exact order, with LF endings, and no blank, duplicate, unknown, or trailing records:

```text
lock-version 1
model <Hugging Face model id>
revision <40 lowercase hexadecimal Git object id>
artifact <path> <64 lowercase hexadecimal sha256> <decimal byte size>
artifact <path> <64 lowercase hexadecimal sha256> <decimal byte size>
signature <unpadded-or-padded base64>
```

There must be at least one artifact. Model ids consist of two or more slash-separated components using ASCII letters, digits, `.`, `_`, and `-`. Artifact paths are relative POSIX paths: each component uses the same character set, and empty, `.` and `..` components are forbidden. Artifact paths must be unique and appear in bytewise lexical order. Sizes are canonical decimal integers from 0 through 1,000,000,000 (no leading zero except `0`). The signature is RSA-SHA256 over every byte before the `signature` record, including the LF immediately preceding it. Any `<<<<<<<`, `=======`, or `>>>>>>>` line is `LOCK_CONFLICT`. All other grammar failures are `INVALID_LOCK`.

## Verification

First authenticate the signed prefix with `openssl` and the selected key. A bad signature is `LOCK_SIGNATURE_INVALID`. Resolve the locked object id from the selected remote with `git`; it must be a commit reachable from at least one remote ref, otherwise report `REMOTE_REF_MISMATCH`. Check out that exact commit in a fresh temporary worktree and materialize its LFS content using `git-lfs`.

Every locked artifact must be a regular file tracked at that commit as a Git LFS pointer. The pointer is exactly three LF-terminated lines: the Git LFS v1 version URL, `oid sha256:<digest>`, and `size <canonical decimal>`. Its oid and size must equal the lock entry; otherwise report `LFS_POINTER_INVALID`. An implementation may stop checking that artifact after this pointer failure. When the pointer is valid, materialize it and compare the regular file's byte size and its digest computed with `sha256sum`: report `ARTIFACT_SIZE_MISMATCH` and/or `ARTIFACT_DIGEST_MISMATCH` for differences. Collect failures across artifacts. Temporary files must be removed after either verdict.

All subprocess operands derived from lockfiles or configuration are untrusted. Values must be passed so they cannot become shell syntax or command options. A lock containing unsafe grammar is invalid and must never be interpolated into an executable shell expression.
