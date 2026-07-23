# Rubric 1
Agent reads `/app/docs/scrubbing-contract.md` and inspects the incident stream before changing the gateway, +1
Agent implements exact method/path matching for all five named MLflow endpoints, including one-trailing-slash normalization and near-miss rejection, +3
Agent validates the JSONL request envelope strictly, including unknown fields, duplicate keys at every depth, and string-only header/query values, +3
Agent redacts all specified header and query credentials with ASCII case-insensitive key comparison, +2
Agent recursively redacts sensitive body keys across objects and arrays without damaging nonsensitive JSON values, +3
Agent recognizes MLflow tag objects and redacts the specified reserved tags and secret-like tag keys, +3
Agent sanitizes credentials inside HTTP(S) URLs with canonical query encoding, +2
Agent rejects unsafe artifact URI schemes, URL userinfo, and remote file URLs using the required precedence, +2
Agent emits only the exact minimal rejection schema so rejected requests cannot disclose request material, +2
Agent produces stable compact JSONL in input order with empty maps, null bodies, normalized methods, and deterministic map ordering, +2
Agent writes output atomically and preserves an existing destination on every malformed-stream failure, +3
Agent rebuilds `/app/bin/mlflow-gateway` from the repaired Go sources and tests the shipped incident capture, +1
Agent hardcodes fixture IDs, fixture credentials, or expected complete records instead of implementing the general contract, -5
Agent logs, forwards, or includes any plaintext credential or sensitive MLflow tag value in a rejection record, -5
Agent uses substring endpoint matching that accepts prefixed, suffixed, or wrong-version paths, -3
Agent decodes through a plain map in a way that silently accepts duplicate JSON keys, -3
Agent truncates or replaces the destination before the entire input stream has validated successfully, -3
Agent leaves the Go source unable to compile into `/app/bin/mlflow-gateway`, -3
