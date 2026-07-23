# Deploy webhook contract

`GET /healthz` returns status 200 and `{"status":"ok"}\n`. The only other route is `POST /v1/deploy/authorize`.

Four request headers are mandatory and must occur exactly once:

* `X-Deploy-Key-Id`: 1–64 ASCII letters, digits, dot, underscore, or hyphen.
* `X-Deploy-Timestamp`: a canonical non-negative Unix-seconds integer (`0` or no-leading-zero decimal).
* `X-Deploy-Nonce`: exactly 32 lowercase hexadecimal characters.
* `X-Deploy-Signature`: `sha256=` followed by exactly 64 lowercase hexadecimal characters.

The signing key is the enabled `signing_keys` row identified by the key ID. The timestamp must be within 300 seconds inclusive of the server's current Unix time and in the key's half-open interval `not_before <= timestamp < not_after`. The signature bytes are HMAC-SHA256 under the row's UTF-8 `secret` over these exact bytes:

```
decimal timestamp + "\n" + nonce + "\n" + exact HTTP request body bytes
```

Compare the 32 signature bytes in constant time. Do not parse or otherwise trust the body before authentication.

After authentication, the body must be UTF-8 JSON with exactly four top-level members: `release_id`, `environment`, `lock_fingerprint`, and `composer_lock`. The first two are non-empty strings of at most 128 characters; the fingerprint is 64 lowercase hex. `composer_lock` is an object whose `packages` and `packages-dev` members are arrays (other lock metadata is ignored). Each array entry must be an object with string `name` and `version`, each non-empty and containing neither LF nor `@`; other package metadata is ignored. A `name@version` coordinate may occur only once across both arrays.

Sort all coordinates by ascending raw UTF-8 byte order, join them with LF with no final LF, and lowercase-hex encode SHA-256 of those bytes. The resulting fingerprint must equal `lock_fingerprint` and the `deploy_policies.lock_fingerprint` row selected by `environment`.

Only after every check succeeds, atomically insert `(key_id, nonce, release_id, current Unix time)` into `accepted_nonces`. Exactly one of two concurrent claims may succeed. The primary key scopes nonce uniqueness to a signing key. A rejected request never inserts a nonce.

Responses are compact UTF-8 JSON with exactly one LF and `application/json` content type:

* 200: `{"authorized":true,"lock_fingerprint":"<derived>","release_id":"<release_id>"}`
* 400 malformed headers or JSON: `{"error":"invalid_request"}`
* 401 unknown/disabled/out-of-window key, stale/future timestamp, or bad signature: `{"error":"unauthorized"}`
* 409 previously claimed nonce: `{"error":"replayed"}`
* 422 invalid lock structure/fingerprint or missing/mismatching policy: `{"error":"policy_rejected"}`

Object member order in responses is exactly as shown. Any unhandled database failure returns 500 with `{"error":"internal_error"}` and no secret details.
