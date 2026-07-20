# ForgeGate admission contract, revision 3

This document defines the offline OCI profile accepted by ForgeGate. Keywords MUST, MUST NOT and MAY are normative.

## Invocation and inputs

The only public operation is:

```
/app/bin/forgegate evaluate --layout DIR --policy FILE --keyring FILE --waivers FILE --out DIR
```

All paths may point outside `/app`. `DIR` is an OCI image-layout directory. Evaluation never uses the network or wall clock: every temporal decision uses `evaluation_time` from the policy. A completed evaluation returns zero and replaces `OUT`; malformed CLI arguments or an unreadable top-level input return 2 without a partial output tree.

JSON called *canonical* in this contract is UTF-8, recursively key-sorted, compact (no insignificant whitespace), and followed by one LF when stored as an artifact. Digests have the lowercase form `sha256:` plus 64 hexadecimal digits.

## OCI image-layout profile

`oci-layout` must equal `{"imageLayoutVersion":"1.0.0"}` semantically. `index.json` is an OCI image index with schemaVersion 2 and media type `application/vnd.oci.image.index.v1+json`. Its manifest descriptors must have exactly `mediaType`, `digest`, `size`, and `platform`; `platform` has `os`, `architecture`, and optional `variant`. Platform identity is `os-architecture` plus `-variant` when present.

Every descriptor is a content commitment. Its digest and byte size must match the regular, non-symlink file at `blobs/sha256/<hex>`. A manifest descriptor names an OCI image manifest with schemaVersion 2 and media type `application/vnd.oci.image.manifest.v1+json`. A manifest has one config descriptor and at least one layer descriptor. Config media type is `application/vnd.oci.image.config.v1+json`; layer media types may be the OCI tar or gzip-tar layer types. Descriptors contain only `mediaType`, `digest`, and `size`.

All referenced config and layer blobs must satisfy their descriptor. The config JSON must declare `os` and `architecture` equal to the index platform; its optional `variant` must also match exactly. Duplicate platform identities, duplicate manifest digests, unrequested platforms, missing requested platforms, unsafe blob paths, non-regular blobs, and any descriptor or media-type violation make the layout globally invalid.

The index digest reported by ForgeGate is the SHA-256 digest of the exact `index.json` bytes. Descriptor annotations are not trusted evidence and are not part of this profile.

## Provenance envelopes

For each selected manifest digest `sha256:H`, the layout contains `evidence/H.provenance.json`. It is an object with exactly `payload` and `signatures`.

The payload has exactly:

```
{
  "builder_id": string,
  "build_finished": RFC3339 UTC instant with millisecond precision,
  "build_started": RFC3339 UTC instant with millisecond precision,
  "commit": 40 lowercase hexadecimal characters,
  "materials": [{"digest": digest, "uri": string}, ...],
  "ref": string,
  "source_uri": string,
  "subject_digest": digest,
  "vulnerabilities": [{"advisory": string, "package": string, "severity": "critical"|"high"|"medium"|"low"}, ...]
}
```

No extra fields are allowed. Materials must be nonempty, have unique URIs, be ordered by URI bytes, and use SHA-256 digests. Vulnerabilities must be unique by `(advisory, package)` and ordered by those two fields as bytes. `build_started` must not be later than `build_finished`; neither may be after policy `evaluation_time`.

Each signature object has exactly `key_id` and `signature`. `signature` is strict standard Base64 for an Ed25519 signature over the exact canonical JSON bytes of `payload` with no trailing LF. A key ID contributes at most once even if repeated. The key must belong to the payload's builder, be active at `build_finished` (`active_from <= time < active_until` when an end exists), and not be revoked at or before that instant. ForgeGate must satisfy both the policy's total signature threshold and every role minimum using distinct valid keys. Unknown, ineligible, malformed, and invalid signatures do not contribute.

## Keyring and policy

The keyring has `keys`, an array of records with exactly `key_id`, `builder_id`, `role`, `public_key_pem`, `active_from`, `active_until`, and `revoked_at`. Nullable times are JSON null. Key IDs are unique. Times use the same instant format as provenance. Public keys are Ed25519 PEM public keys.

The policy has exactly:

```
{
  "allowed_builders": [{"builder_id": string, "source_prefix": string, "ref_glob": string}],
  "evaluation_time": instant,
  "image": string,
  "platforms": [{"architecture": string, "os": string, optional "variant": string}, ...],
  "role_minimums": {role: positive integer, ...},
  "signature_threshold": positive integer,
  "trusted_material_prefixes": [string, ...]
}
```

Arrays that act as sets must not contain duplicates. A builder is allowed only by the record with its exact ID. Its source URI must begin with that record's literal `source_prefix`. Its ref must match `ref_glob`, where `*` matches any bytes and every other character is literal. Every material URI must begin with at least one trusted material prefix. The provenance subject must equal the selected manifest digest.

## Vulnerability waivers

The waiver file has `waivers`, an array. Every waiver has exactly `id`, `image`, `platform`, `advisory`, `package`, `builder_id`, `source_prefix`, `commit`, `starts_at`, and `expires_at`. IDs are unique. `commit` may be a 40-character lowercase commit or null. A waiver covers one vulnerability only when every non-temporal field matches: image, platform, advisory, package and builder are exact; source uses literal-prefix matching; and a non-null commit is exact. It is active when `starts_at <= evaluation_time < expires_at`. Invalid or inverted waiver intervals never match.

Critical and high vulnerabilities require a matching active waiver. Medium and low findings are reported but do not prevent admission. The output lists only the IDs of waivers actually consumed, byte-sorted and without duplicates.

## Verdicts and precedence

Unreadable or invalid top-level JSON, an invalid keyring or policy, or any OCI graph failure produces one global rejected report with reason `LAYOUT_INVALID` and no admission files. Once the layout is valid, each requested platform is evaluated independently. Its reasons appear in this fixed order when applicable:

1. `PROVENANCE_MISSING`
2. `PROVENANCE_MALFORMED`
3. `SUBJECT_MISMATCH`
4. `SIGNATURE_POLICY_UNMET`
5. `BUILDER_NOT_ALLOWED`
6. `SOURCE_NOT_ALLOWED`
7. `REF_NOT_ALLOWED`
8. `COMMIT_INVALID`
9. `BUILD_TIME_INVALID`
10. `MATERIAL_NOT_TRUSTED`
11. `VULNERABILITY_UNWAIVED`

Malformed provenance ends that platform's evaluation with only `PROVENANCE_MALFORMED`. Missing provenance similarly yields only `PROVENANCE_MISSING`. Other applicable reasons accumulate in the order above. A platform is admitted only when its reasons are empty. The image is admitted only when every requested platform is admitted.

## Output

`OUT/report.json` is canonical JSON with exactly:

```
{
  "evidence_digest": hex SHA-256 without prefix,
  "image": policy image,
  "index_digest": digest or null,
  "platforms": [platform verdicts ordered by platform bytes],
  "status": "admitted"|"rejected"
}
```

A platform verdict has exactly `platform`, `manifest_digest`, `status`, `reasons`, `builder_id`, `source`, `commit`, `signers`, `waivers`, and `findings`. Unknown descriptive values are null. `signers` contains the byte-sorted contributing key IDs. `findings` is the provenance vulnerability array. For malformed or missing evidence it is empty. The evidence digest is SHA-256 over canonical JSON bytes (without LF) of the complete `platforms` array.

For each platform, ForgeGate writes the identical verdict object to `OUT/admission/<platform>.json`. No other files may remain in `OUT`. On a globally invalid layout, `platforms` is empty, `index_digest` is null, `status` is rejected, and the report additionally contains `reasons:["LAYOUT_INVALID"]`; its evidence digest commits to the empty array.
