# Reference approach

The reference implementation separates probing, graph parsing, and attestation. Paths are resolved and checked before `exec.Command` launches FFprobe with a fixed argument vector. Its JSON is decoded with `UseNumber`; only the contract fields survive, numeric strings are normalized, and streams are sorted before compact JSON is hashed.

GraphML is parsed into a deliberately narrow XML model. Key declarations map GraphML key IDs to semantic attribute names, which prevents signatures from depending on incidental XML key identifiers. Each edge is bound to its ID, endpoints, relative media path, and freshly computed probe digest through a NUL-delimited, domain-separated Ed25519 message.

Verified edges are sorted by ID. Leaves hash the domain and canonical edge object; parents hash a different domain plus raw child digests. An unpaired node is duplicated. The final report uses structs (not maps), compact JSON, and a trailing newline, making API and CLI output identical.
