# Rubric

Agent inspects the contract and fixture before modifying the Go gateway, +1
Agent implements strict JSON parsing with duplicate-key, schema, integer, and sequence validation, +4
Agent performs exact MLflow method/path classification and required normalization with correct rejection precedence, +3
Agent recursively redacts all specified header, body, and MLflow tag secrets, +4
Agent canonicalizes secret-bearing HTTP(S) URLs and rejects all unsafe URI cases, +3
Agent emits minimal rejection records that disclose no request material, +2
Agent constructs exact canonical base records with stable Go JSON encoding and required defaults, +3
Agent computes every SHA-256 chain value from the decoded seed, previous digest bytes, and exact base-record bytes, +4
Agent validates the lowercase seed and writes the complete output atomically, +3
Agent rebuilds and exercises `/app/bin/mlflow-audit`, +1
Agent hardcodes fixture records, secrets, or chain values, -5
Agent silently accepts duplicate keys, repeated/decreasing sequences, or malformed envelopes, -4
Agent hashes hex text, includes a newline or `chain` in the hash input, or resets the chain per record, -4
Agent leaks request data in a rejected record or any specified secret in output, -5
Agent truncates/replaces an existing destination before all input validates, -4
