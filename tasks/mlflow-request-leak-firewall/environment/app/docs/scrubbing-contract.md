# MLflow migration scrubbing contract

The program consumes UTF-8 JSON Lines. Blank lines are ignored. Every nonblank line is one request object with exactly these top-level fields: `id` (nonempty string), `method` (string), `path` (string), and optional `headers` (object of string values), `query` (object of string values), and `body` (any JSON value). Unknown top-level fields, duplicate JSON keys at any depth, invalid JSON, non-string header/query values, and missing required fields are malformed. One malformed line is fatal: exit nonzero and do not create or replace the output file.

## Endpoint policy

Before matching, separate any `?query` suffix, then strip one trailing slash from the path portion (except `/`); percent escapes are not decoded. Match that normalized path portion and uppercase method against this table only. The original presence of a query suffix is still handled by the secret policy below.

| route name | method | path |
|---|---|---|
| `create_run` | POST | `/api/2.0/mlflow/runs/create` |
| `log_batch` | POST | `/api/2.0/mlflow/runs/log-batch` |
| `set_tag` | POST | `/api/2.0/mlflow/runs/set-tag` |
| `get_run` | GET | `/api/2.0/mlflow/runs/get` |
| `artifact_uri` | GET | `/api/2.0/mlflow/artifacts/get-download-uri` |

An exact supported path with the wrong method is rejected as `method_not_allowed`; every other path is rejected as `unsupported_endpoint`. Classification happens before the body policy.

## Secret policy

Accepted records contain scrubbed copies of headers, query, and body. Rejected records contain no request data. Header and query key comparison is ASCII case-insensitive. Replace values of `authorization`, `proxy-authorization`, `cookie`, `set-cookie`, `x-api-key`, `x-mlflow-token`, `token`, `access_token`, `refresh_token`, `x-amz-credential`, `x-amz-signature`, `x-amz-security-token`, and `sig` with the literal `[REDACTED]`.

Recursively walk JSON objects and arrays in `body`. Replace a scalar value with `[REDACTED]` when its object's key, compared case-insensitively, is one of `password`, `passwd`, `secret`, `client_secret`, `token`, `access_token`, `refresh_token`, `api_key`, `authorization`, `credential`, `x-amz-credential`, `x-amz-signature`, or `x-amz-security-token`. If such a key has an object or array value, replace the entire value. In any object containing string fields `key` and `value`, also redact `value` when `key`, compared case-insensitively, is `mlflow.user`, `mlflow.source.name`, `mlflow.source.git.commit`, or contains any of the substrings `password`, `secret`, `token`, `credential`, or `api_key`.

Every body string whose parsed URL uses scheme `http` or `https` must also have sensitive query parameters redacted by the query-key rules above. Preserve all other URL components and parameters. Encode query parameters using Go's canonical `url.Values.Encode()` order. Non-URL strings stay unchanged. Apply key-based replacement before URL handling.

After scrubbing, reject an otherwise supported request as `credential_in_path` if its path contains user information (`scheme://user@host`) or a query component. (Normal MLflow paths do not.) Reject it as `unsafe_artifact_uri` if any body URL has a nonempty userinfo, uses a scheme other than `http`, `https`, `s3`, `gs`, `wasbs`, `dbfs`, or `file`, or if a `file` URL has a host. Rejection reasons use the precedence: endpoint classification, `credential_in_path`, then `unsafe_artifact_uri`.

## Output

Write one compact JSON object per input request in input order, using Go JSON encoding (HTML escaping disabled), followed by `\n`. Accepted schema:

`{"id":string,"decision":"forward","route":string,"request":{"method":UPPERCASE_STRING,"path":NORMALIZED_PATH,"headers":object,"query":object,"body":JSON}}`

The three request maps are always present; absent headers/query become `{}` and absent body becomes `null`. Rejected schema is exactly `{"id":string,"decision":"reject","reason":string}`. Object key ordering must be stable and repeated runs over identical bytes must be byte-identical. Write atomically: create a temporary file beside the output, sync and close it, then rename it over the destination only after all input was successfully processed.
