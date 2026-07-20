# Close the vulnerabilities in the ReleaseSentinel attestation verifier

ReleaseSentinel at `/app` is the supply-chain trust gate: nothing ships unless it certifies that a release artifact is authentic. It ingests *release badges* — PNG files carrying an Ed25519-signed attestation inside one or more private ancillary chunks of type `atSt` — verifies the signature, decides whether the signing key had any authority to vouch for that release, and reconciles the claim against our release repository. An audit of the verifier just came back and it is not enforcing any of that.

It has a **signature-verification bypass**: attestations are accepted without the signature ever being checked against the statement it covers, so a forged or tampered badge is certified as genuine. It has a **memory-corruption vulnerability**: badges are attacker-supplied input, and the native parser writes and reads outside its buffers on hostile or merely unusual input, dying on some badges and silently truncating the attestation on others — meaning a badge can be judged on a payload that is not the one that was signed. And it **fails to enforce key revocation**: a signing key compromised earlier this year, and keys with no authority to sign a release at all, are still being honoured.

Close all three. The native extractor under `/app/native` must be memory-safe on every badge it is handed, including malformed and truncated ones — no out-of-bounds reads or writes, no leaks — while keeping the ABI declared in `/app/native/attest.h`. The verification and trust logic in the Java worker under `/app/src` must be completed. `make -C /app all` must still rebuild `/app/build/libattest.so` and `/app/build/sentinel.jar` from source.

## The signed attestation

A badge's payload is the concatenation, in file order, of the data of every `atSt` chunk (one payload is frequently split across several). Decoded as UTF-8 it is JSON of this shape:

```json
{
  "signature": "<base64 Ed25519 signature>",
  "statement": {
    "artifact_digest": "sha256:<64 lowercase hex characters>",
    "issued_at": "2026-05-12T09:14:00.000Z",
    "key_id": "k-build-2026a",
    "release_branch": "release/8.4",
    "release_tag": "v8.4.0",
    "service": "payments-api"
  }
}
```

The statement carries exactly those six members, each a non-empty string, and `issued_at` uses exactly the form `YYYY-MM-DDTHH:mm:ss.sssZ`. The signature is Ed25519 over the **canonical** serialization of the `statement`: object keys sorted by Unicode code point, recursively; compact UTF-8 JSON; no insignificant whitespace; no trailing newline. The signature must be verified against those exact bytes — verify against anything else and a tampered statement still passes.

A badge is unreadable when it carries no `atSt` chunk, when any chunk's CRC-32 fails to verify, when the payload is not valid UTF-8 JSON, or when it does not match the shape above. Public keys are in `/app/config/keyring.json`; that file is key material only, and a key's presence there says nothing about whether it is permitted to vouch for a release.

## The trust policy

Which keys may sign a release, when a key's authority lapses, which service holds a standing exception to keep using a retired key and until when, when the previous build key stopped being acceptable, and how a badge's claimed branch is reconciled against the repository — none of this is written down in one place. It was argued out and settled across the release-security war room, archived under `/app/docs/incident-room/`. Reconstruct the policy in force from that history, including the parts where an early decision was later reversed and where people misremember what was agreed.

The repository at `/app/repo` is the source of truth for tags: a tag exists only if it is a real git tag, and the branch a tag was cut from is the branch named in that tag's heading in `/app/repo/CHANGELOG.md`. A badge's own claim about its branch is an assertion by the thing being audited, not evidence.

## Verdicts

Run as `java -Djava.library.path=/app/build -jar /app/build/sentinel.jar snapshot --badges <dir> --repo <dir> --keyring <file> --out <file>`, the verifier audits every `*.png` in the badge directory and writes an audit snapshot to the output path.

Each badge gets exactly one verdict. Where more than one could apply, the first of these wins:

1. `badge_unreadable` — the payload cannot be read or parsed.
2. `key_untrusted` — the key id is absent from the keyring, or that key has no authority to sign a release badge at all.
3. `signature_invalid` — the signature does not verify over the canonical statement.
4. `key_revoked` — the key's authority had lapsed for this statement, given when it was issued and any exception that applies.
5. `tag_unknown` — the release tag is not a tag in the repository, or has no changelog heading.
6. `branch_conflict` — the branch the badge claims disagrees with the branch the changelog attributes to that tag, and the policy does not tolerate the discrepancy.
7. `accepted` — otherwise.

## The audit snapshot

Canonical JSON — recursively sorted keys, compact UTF-8, no insignificant whitespace — plus exactly one trailing newline, with exactly three members.

`badges` is an array, ordered by badge filename, of one object per badge holding exactly `badge` (the filename), `service`, `key_id`, `release_tag`, `release_branch`, `exception_id` and `status`. The descriptive fields depend on the verdict:

- `badge_unreadable`: nothing could be read, so `service`, `key_id`, `release_tag`, `release_branch` and `exception_id` are all null.
- `key_untrusted`, `signature_invalid`, `key_revoked`, `tag_unknown`: the badge was rejected before it was ever reconciled against the repository, so `service`, `key_id`, `release_tag` and `release_branch` are recorded exactly as the statement claimed them, and `exception_id` is null.
- `branch_conflict`, `accepted`: the tag was reconciled, so `release_branch` is the branch the changelog attributes to the tag — which for `branch_conflict` is by definition not the one the badge claimed. `exception_id` names the exception that permitted an otherwise-revoked key, or is null.

`counts` maps each of the seven verdicts to how many badges hold it, including verdicts with a count of zero. `digest` is the lowercase SHA-256 hex digest of the canonical bytes of the `badges` array, so an audit can be cited by hash. Consequently, reformatting a badge's JSON, reordering statement keys, or re-splitting the payload across `atSt` chunks must leave the snapshot bytes identical, while any change to what a badge attests must change the digest.

`/app/fixtures/badges` holds example badges to audit; leave them in place.
