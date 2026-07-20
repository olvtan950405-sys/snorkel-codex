# #war-room-releasesentinel

## 2026-04-20

**08:41 priya.raghunathan**
Morning. Opening a room because something turned up in the overnight badge audit that I don't like. The release-badge bucket has objects signed by `k-ci-sandbox`. That's the sandbox pipeline's key. It should not be anywhere near a release badge. Not a huge count yet. But "yet" is doing work in that sentence.

**08:43 priya.raghunathan**
Here's what the auditor spat out. This is the `key_id` field pulled out of the attestation on every object under the release prefix in the last 24h:

```
$ aws s3 ls s3://northwind-release-badges/ --recursive | grep '\.png$' | wc -l
418
$ ./badge-audit --prefix s3://northwind-release-badges/ --since 24h --group-by key_id
  k-build-2026a   403
  k-build-2025b     9
  k-ci-sandbox      6
```

Six of them. Six release badges signed by a key that has no business signing a release.

**08:45 ola.ferrand**
Well good morning to you too. Six out of four-eighteen. Before anyone reaches for the fire axe — where are they and what do they claim to be?

**08:46 priya.raghunathan**
Pulling the object list now.

**08:47 priya.raghunathan**
```
$ aws s3 ls s3://northwind-release-badges/ --recursive | grep -E 'payments|orders|search'
2026-04-20 02:11:33  184402  payments-api/v8.4.0/badge.png
2026-04-20 02:11:34  184402  payments-api/v8.4.0/badge-abcd12f.png
2026-04-20 02:14:07  183118  orders-api/v8.4.0/badge.png
2026-04-20 03:02:55  191774  search-api/v8.4.0/badge.png
...
2026-04-20 04:19:20  177213  payments-api/_promoted/badge-sbx-9f21a3c.png
2026-04-20 04:19:21  177213  payments-api/_promoted/badge-sbx-1b77e04.png
2026-04-20 04:22:48  176980  orders-api/_promoted/badge-sbx-2c0119d.png
2026-04-20 04:22:49  176980  orders-api/_promoted/badge-sbx-6ae5f80.png
2026-04-20 04:31:12  178330  search-api/_promoted/badge-sbx-40de8b1.png
2026-04-20 04:31:13  178330  search-api/_promoted/badge-sbx-b3c2210.png
```

**08:47 priya.raghunathan**
The six under `_promoted/` with the `badge-sbx-` prefix. All six landed between 04:19 and 04:31.

**08:48 kenji.watanabe**
`badge-sbx-` is not subtle. Those are sandbox artefacts, somebody parked sandbox output in the release bucket. Note the naming too: the real ones are `v8.4.0/badge.png`, the sandbox ones sit under a `_promoted/` folder with a git-shortsha suffix and no tag directory. Different shape entirely.

**08:50 priya.raghunathan**
Right, and normally I'd say "different folder, worker never looks there" and go back to bed. But I checked: the worker's scan config globs `**/badge*.png` under the release bucket root. So it does look there.

**08:51 ola.ferrand**
It does. The scan glob is `s3://northwind-release-badges/**/badge*.png`. `_promoted/badge-sbx-*.png` matches. The worker will pick those up on the next sweep and try to verify them like any other release badge.

**08:52 priya.raghunathan**
So let's be precise about what "verify" does with them. Ping @dana.whitfield — you own the keyring, you're going to want to see this.

**08:54 dana.whitfield**
Seeing it. Give me two minutes, I'm pulling one of the objects and cracking the attestation open.

**08:59 dana.whitfield**
OK. Grabbed `payments-api/_promoted/badge-sbx-9f21a3c.png` and extracted the `atSt` payload out of it by hand. Here's the statement, redacted only for width:

```json
{
  "signature": "u4kQ...9dQ==",
  "statement": {
    "artifact_digest": "sha256:7b1e0c9a44f2e1b8c0d3aa5510f2c6e1d99b4477ac30e2b6d1f8a0c3e4551029",
    "issued_at": "2026-04-20T04:18:52.114Z",
    "key_id": "k-ci-sandbox",
    "release_branch": "release/8.4",
    "release_tag": "v8.4.0",
    "service": "payments-api"
  }
}
```

**09:00 dana.whitfield**
So this is the part that will make people angry, and I want to get ahead of it. The signature on this thing is *valid*. I verified it. `k-ci-sandbox` is in `/app/config/keyring.json`, I have its public key, and the Ed25519 signature over that statement checks out byte for byte. Nothing is forged. The sandbox pipeline signed a genuine, well-formed attestation with a key it genuinely holds.

**09:01 dana.whitfield**
The problem is not that the signature is bad. The problem is that this key is not allowed to say this sentence. `k-ci-sandbox` has no authority to attest a release. It can sign whatever it likes in the sandbox; that's its job. It cannot vouch for a payments-api release, and this object is claiming exactly that.

**09:02 marcus.lin**
Hold on. If the signature verifies and the key's in the keyring, what's actually wrong? The digest is real, right? Is the artefact it points at even a bad artefact?

**09:03 dana.whitfield**
The artefact might be completely fine. That's not the question. The question is who signed the attestation, and whether that signer is permitted to make a release claim. It isn't.

**09:03 marcus.lin**
So it's a bad signature.

**09:04 dana.whitfield**
No. Stop — this is the exact confusion I need to kill before it spreads, because if the war room walks out of here thinking "bad signature" we will build the wrong thing.

**09:05 dana.whitfield**
It is not a bad signature. The signature is cryptographically valid. If you ran the raw Ed25519 verify you would get `true`. There is nothing wrong with the bytes.

**09:06 dana.whitfield**
What's wrong is *trust*. Signature-validity answers "did the holder of key K sign these bytes?" — and the answer here is yes. Trust answers a completely different question: "is key K allowed to attest a release?" — and the answer here is no. `k-ci-sandbox` is untrusted for release attestation. Two separate verdicts. A badge can pass the first and fail the second, and that is precisely what is happening with all six of these.

**09:07 dana.whitfield**
So the verdict the worker must return for these objects is **untrusted key**. Not "invalid signature". Not "verification failed". Untrusted key. The signature checked out and the key still has no authority. Those words matter and I'll die on this hill.

**09:08 kenji.watanabe**
That's a good distinction and it's easy to get backwards. For what it's worth the way I'd phrase it to someone: the signature question is "is this real?" and the trust question is "does this key get a vote?". Sandbox key is real and gets no vote.

**09:10 ola.ferrand**
Noted on the worker side. So for these six the terminal state is `UNTRUSTED_KEY`, not any of the signature-failure states, and I want that to be a distinct outcome in the report — the two mean opposite things operationally. A bad signature means someone tampered or the build is broken. An untrusted key means the signature is fine and the *signer* is wrong.

**09:11 priya.raghunathan**
Agreed, keep them distinct. If on-call sees "invalid signature" they'll go hunt a tampering incident that doesn't exist. "Untrusted key: k-ci-sandbox" tells them it's plumbing.

**09:13 yusuf.adeyemi**
late, catching up, don't mind me. ok so search-api has two of these under `search-api/_promoted/`. is search on fire or is this a bucket-hygiene thing

**09:14 priya.raghunathan**
Bucket hygiene, so far. Nobody shipped a bad search release. Sandbox output leaked into the release bucket. We're arguing about how the worker should treat it and where it came from. Scroll up for dana's trust-vs-signature bit, it's the important part. And to answer the obvious question: the 403 `k-build-2026a` and 9 `k-build-2025b` badges are untouched and fine. Only the 6 `k-ci-sandbox` ones are the issue.

**09:18 tomas.berg**
Right, I've read the whole thing now and I have a much simpler proposal than all this verdict-taxonomy talk. Delete `k-ci-sandbox` from the keyring. If the key isn't in `/app/config/keyring.json`, the worker can't verify anything signed by it, the sandbox badges become unverifiable, they get rejected, and we never have to have the "untrusted vs invalid" conversation again because there's no key to be untrusted. One-line change to the keyring. Done.

**09:19 tomas.berg**
It has no business being in a *release* keyring in the first place. Why is the sandbox key sitting in the same file as the production build keys? That's the actual bug.

**09:20 marcus.lin**
+1 tomas. That's clean. Take the sandbox key out and the whole class of problem disappears. I've got the 8.4.1 cut breathing down my neck, I don't want to babysit a taxonomy.

**09:21 dana.whitfield**
No. I understand why it looks clean and it is the wrong move. Let me explain why, because if I just say "no" someone will do it on a Friday and page me.

**09:22 dana.whitfield**
`k-ci-sandbox` is in the keyring on purpose. The sandbox pipeline needs its public key published there. That is not an accident of history, it's load-bearing.

**09:23 dana.whitfield**
Here is the flow you'd be breaking. The sandbox pipeline builds candidate artefacts and signs its own sandbox badges with `k-ci-sandbox`. Before anything is allowed to *become* a real release candidate, there's a promotion gate — call it the sandbox promotion gate — that re-verifies the sandbox badge to prove the artefact it's about to promote is the exact artefact the sandbox actually built and signed, and not something swapped in between. That gate verifies the sandbox badge against `k-ci-sandbox`. To do that, it needs `k-ci-sandbox`'s public key. It reads it from the same published keyring. Pull the key and the promotion gate can't verify sandbox badges anymore and the gate fails closed. You'd wedge every promotion out of sandbox across all three services.

**09:24 tomas.berg**
Then the promotion gate should read the sandbox key from somewhere else. A separate file. It doesn't need to be in the *release* keyring to do that.

**09:25 dana.whitfield**
It could, in a different world where we maintained two keyrings and kept them in sync and audited both. We maintain one. `/app/config/keyring.json` is the one published keyring, it holds public key material for every key the platform verifies against, sandbox included, and it deliberately holds *nothing about trust*. It doesn't say k-build-2026a is allowed to sign releases either. It's just public keys. The keyring answers exactly one question: "here is the public key for key_id X." Whether X is *allowed* to sign a release is not in that file and was never meant to be — that policy lives in decisions like the one we're making right now. Fork it into two keyrings and the drift between them becomes the new incident. I've watched that movie.

**09:27 kenji.watanabe**
This matches what bit me last quarter, honestly. I went looking in `keyring.json` for a "can this key sign releases" flag and there isn't one, and dana explained then that there's deliberately no trust metadata in there. So "delete the key to encode 'not trusted'" is smuggling a trust decision into a file that has no trust semantics. The key being present means "we can verify its signatures", nothing more.

**09:28 tomas.berg**
Fine, I hear the promotion-gate argument, that's the bit I didn't have. If pulling the key wedges promotion for all three services then pulling the key is off the table. I still think it's ugly that the sandbox key and the prod build key live in the same file with nothing distinguishing them, but ugly isn't the same as wrong and I'm not going to blow up promotion to satisfy my sense of tidiness.

**09:29 tomas.berg**
So the key stays. Recording that so nobody re-opens it in three weeks: `k-ci-sandbox` stays in the keyring. Deletion rejected because it breaks the sandbox promotion gate.

**09:29 dana.whitfield**
Thank you. Yes. Key stays.

**09:30 marcus.lin**
ok, key stays, I withdraw the +1. so if we're not removing the key, what stops the sandbox badges from being trusted? because the worry that started this is release badges signed by the sandbox key, and the key is still in the keyring, so the signature still verifies.

**09:31 dana.whitfield**
Right, and this is where the trust-vs-signature distinction earns its keep, so it's good you asked. The signature verifying is fine and expected — the key is in the keyring precisely so its signatures verify, for the promotion gate. What we add on top is the trust rule: `k-ci-sandbox` may never sign a *release* badge. If the worker sees a release badge whose `key_id` is `k-ci-sandbox`, it rejects it as an untrusted key. The signature verifying is irrelevant to that verdict. The key simply has no authority to attest a release, full stop, regardless of whether the bytes check out.

**09:33 ola.ferrand**
For the worker that's clean to implement as a rule, independent of the signature path. Even if someone handed us a sandbox badge with a garbage signature, the answer is still untrusted key — we don't get to "the signature is bad" because the key was never allowed to sign this in the first place.

**09:34 dana.whitfield**
Correct, and that ordering is deliberate. Authority first. If the signer isn't allowed to make the claim, the validity of the claim's signature is moot.

**09:35 priya.raghunathan**
Good. That's the policy. Now the other half: how did six sandbox badges get into `s3://northwind-release-badges/` at all? Because the worker rule is a backstop, it is not an explanation. Something is *writing* these into the release bucket at 4am.

**09:36 ola.ferrand**
The `_promoted/` prefix is the tell. Something is deliberately promoting sandbox output into the release bucket and calling it promotion. Let me pull the object metadata, the writer identity should be on the PutObject.

**09:39 ola.ferrand**
Here's the tags/metadata off one of them:

```
$ aws s3api head-object --bucket northwind-release-badges \
    --key payments-api/_promoted/badge-sbx-9f21a3c.png
{
  "LastModified": "2026-04-20T04:19:20+00:00",
  "ContentLength": 177213,
  "ContentType": "image/png",
  "Metadata": {
    "x-nw-pipeline": "sandbox-promote",
    "x-nw-job": "CI-880",
    "x-nw-commit": "9f21a3c",
    "x-nw-source-bucket": "northwind-sandbox-badges"
  }
}
```

**09:40 ola.ferrand**
`x-nw-job: CI-880`. `x-nw-pipeline: sandbox-promote`. `x-nw-source-bucket: northwind-sandbox-badges`. So there's a job called CI-880 in the sandbox pipeline that is copying badges out of the sandbox badge bucket into the *release* badge bucket. That's the source.

**09:41 kenji.watanabe**
CI-880 is the promotion job. I know that one — it's supposed to promote the built *artefact* into the release artefact registry once the promotion gate passes, and re-stamp the badge into the sandbox archive. It is absolutely not supposed to push the sandbox badge into `northwind-release-badges`. That destination is wrong.

**09:42 priya.raghunathan**
So someone changed CI-880's destination. When?

**09:43 kenji.watanabe**
Pulling the pipeline config history. Give me a sec.

**09:47 kenji.watanabe**
Found it. There's a change to `ci/pipelines/sandbox-promote.yml` merged three days ago, 2026-04-17, in CI-880's config. Here's the diff on the upload step:

```diff
--- a/ci/pipelines/sandbox-promote.yml
+++ b/ci/pipelines/sandbox-promote.yml
@@ -71,10 +71,12 @@ steps:
   - name: archive-sandbox-badge
     image: registry.internal/nw/aws-cli:2.15
     commands:
-      - aws s3 cp $BADGE_PATH \
-          s3://northwind-sandbox-badges/${SERVICE}/_promoted/badge-sbx-${COMMIT}.png
+      - aws s3 cp $BADGE_PATH \
+          s3://northwind-release-badges/${SERVICE}/_promoted/badge-sbx-${COMMIT}.png
+      # promote badge alongside artefact so release dashboards can see sandbox lineage
+      - echo "promoted badge for ${SERVICE}@${COMMIT} to release bucket"
```

**09:48 kenji.watanabe**
There it is. Someone flipped the archive destination from `northwind-sandbox-badges` to `northwind-release-badges`. The commit message on that change is "surface sandbox lineage on release dashboards". Well-meant. Completely wrong bucket.

**09:49 ola.ferrand**
"so release dashboards can see sandbox lineage." I understand the intent and I even sympathise. But the release badge bucket is where the worker looks for things to attest as releases. You don't get to use it as a display shelf for sandbox lineage. The dashboard wanting to *see* the badge is not a reason to put it where the verifier will *trust* the location.

**09:51 kenji.watanabe**
It's under CI-880, merged by the sandbox pipeline squad — not to blame, I'll close the loop with them and take the fix. The archive step goes straight back to `northwind-sandbox-badges/${SERVICE}/_promoted/...` where it was, and if they want lineage on the release dashboard we do that with a metadata pointer, not by copying the badge into the trust bucket. Opening CI-892 to revert.

**09:52 tomas.berg**
Revert plus a note in the pipeline README that `northwind-release-badges` is not a scratch space. People keep treating that bucket like it's just "where PNGs go". It's the input to the attestation worker. Writing to it is a security-relevant act. CI-892 when it's up.

**09:54 marcus.lin**
Great, so once CI-892 lands and the six objects get cleaned out of the release bucket, we're done, right? The job stops copying, the bad objects go away, worker never sees them.

**09:55 dana.whitfield**
No. That's the part I want to nail down before anyone marks this resolved. Fixing CI-880 is necessary and it is not sufficient. The worker must reject sandbox-key release badges *regardless* of how they got into the bucket.

**09:56 dana.whitfield**
The reason is the one tomas just said out loud. The bucket is not a trust boundary. "It's in `northwind-release-badges`" is not evidence that something is a legitimate release. Anything that can write to that bucket — a misconfigured CI job today, a different misconfigured job next quarter, a bug, a bad IAM policy, someone with a laptop and `aws s3 cp` — can put a PNG there. If our only defence against a sandbox badge being trusted is "the promotion job is configured correctly", then our security depends on every CI job that can reach the bucket being correct forever. That's not a defence, that's a hope.

**09:57 dana.whitfield**
The trust decision has to be made by the worker, at verification time, based on the key that signed the attestation. `k-ci-sandbox` signed it, `k-ci-sandbox` is untrusted for releases, reject as untrusted key. That verdict is true whether the badge arrived via CI-880, via CI-899, via a fat-fingered manual copy, or via an actual attacker. The bucket location never enters into it.

**09:58 ola.ferrand**
Strongly agree and it's also just less code. The worker doesn't need to know anything about buckets or promotion jobs or where an object came from. It looks at the `key_id`, applies the trust rule, done. If we tried to defend at the bucket layer we'd be writing IAM policy and S3 event filters to encode a thing that is fundamentally a *key trust* statement. Wrong layer.

**09:59 kenji.watanabe**
Right. CI-892 removes today's *source* of the leak. The worker rule removes the *class*. We want both — otherwise we're one config typo away from doing this all again, and next time maybe nobody's watching the 4am audit.

**10:00 priya.raghunathan**
So to be totally explicit and on the record: even after CI-892 lands, the worker rejecting `k-ci-sandbox` release badges as untrusted key stays permanent policy. It is not a temporary workaround for the CI bug. Yes?

**10:00 dana.whitfield**
Yes. Permanent. The CI fix is cleanup. The worker rule is the policy. Do not let anyone frame the worker rule as "the mitigation until CI-880 is fixed" — that gets it exactly backwards.

**10:01 tomas.berg**
Agreed. The bucket is a delivery mechanism, not an authorization. Well put earlier, dana, "not a trust boundary" — I'm putting that phrase in the README too.

**10:04 ingrid.solberg**
Compliance, arriving with a notebook — how this gets logged is how it'll be read in six months by someone who wasn't here, so let me confirm before I write it down. These six badges are being rejected, and the reason is that the signing key is not authorized to attest releases — an authorization/trust failure — and specifically NOT that the signature was invalid or the artefact was tampered with. Fair statement of it?

**10:05 dana.whitfield**
That is exactly the fair statement and thank you for checking rather than guessing. Reason: untrusted key. `k-ci-sandbox` is not authorized to sign release attestations. The signatures on these six were valid. No tampering. No signature failure. The verdict is about the signer's authority, not the signature's correctness.

**10:06 ingrid.solberg**
Good. Because "invalid signature" and "untrusted key" are not interchangeable in an audit finding and if I logged the wrong one it implies a completely different incident. "Invalid signature" implies a possible attack or corruption. "Untrusted key" implies a policy/authorization control doing its job. This is the second one. The control worked, or will work once the worker rule ships.

**10:08 ingrid.solberg**
Logging it as: six release-bucket badges signed by `k-ci-sandbox`, rejected — key not authorized for release attestation (trust), signatures valid, no artefact tampering, root cause a CI misconfiguration copying sandbox badges into the release bucket, corrected under CI-892, worker-side trust rejection retained as standing control. That capture everyone?

**10:09 dana.whitfield**
That captures it. One tightening: "worker-side trust rejection retained as standing control" — make it clear the control is not contingent on the CI fix. It stands on its own.

**10:09 ingrid.solberg**
Amended. "retained as standing control independent of the CI remediation." Good.

**10:11 priya.raghunathan**
OK. Now the operational question I actually need answered before I close the room. Do we alert on this or not? Six of these showed up overnight and nobody was paged. If the worker starts returning `UNTRUSTED_KEY` for sandbox badges, does that page someone, log quietly, or something in between?

**10:12 marcus.lin**
Please for the love of god do not page on it. If every sandbox badge that leaks into the bucket wakes payments on-call at 4am we will drown. We already page too much. This is a plumbing problem, not a payments-down problem.

**10:13 ola.ferrand**
I lean the same way but for a different reason. A page implies "a human must act now." After CI-892 lands there is no human action for a sandbox badge in the release bucket — the worker rejects it, the release it was pretending to attest doesn't get trusted, nothing ships that shouldn't. The correct handling is fully automatic. Paging on a thing that self-handles is how you train people to ignore pages.

**10:14 dana.whitfield**
I want to push back a little, not to demand a page, but to make sure we don't go all the way to silence. Yes, the worker rejecting the badge is automatic and safe. But "sandbox key showed up on a release badge" is also a *signal*. Today it's a benign CI typo. The exact same signature — sandbox key, release claim — is what you'd expect to see if someone were probing whether they could get a non-authorized key accepted. I don't want that class of event to be invisible just because today's instance is benign.

**10:15 dana.whitfield**
So my position: don't page, but don't drop it on the floor either. It should be a visible, queryable, counted event. If `k-ci-sandbox` starts signing release badges I want to be able to see the rate go up, even if no single instance is worth a 4am page.

**10:16 priya.raghunathan**
That's the distinction I was fishing for. Page = human must act now. This is not that. But "log it and forget it" loses the security signal dana's describing. Middle path: emit a metric and a structured log line on every `UNTRUSTED_KEY` verdict, with the `key_id`, dashboard tile, threshold on the rate.

**10:17 ola.ferrand**
Yes, that I'm happy with. Worker already emits a counter per verdict type. `releasesentinel_badge_verdicts_total{verdict="untrusted_key",key_id="k-ci-sandbox"}`. Right now that counter would read 6 for the overnight window. We put it on the ReleaseSentinel dashboard next to the other verdict counters.

**10:18 priya.raghunathan**
And a low-urgency alert on the *rate*, not a page. If untrusted-key verdicts for a given key exceed some small threshold per hour, it goes to the `#sec-signals` channel as a notification, not to PagerDuty. Benign CI leak: dashboard blips, someone looks in the morning. Actual probing: rate climbs, channel lights up, still no 4am page but we see it fast.

**10:19 dana.whitfield**
That works for me. Visible and counted, not paged. The thing I was defending against was invisibility, not lack of a page.

**10:21 kenji.watanabe**
One more for the alert threshold — after CI-892 lands the steady-state for `untrusted_key{key_id="k-ci-sandbox"}` should be zero. So a *non-zero* rate is itself meaningful once we've cleaned up. Set the notification threshold low. Even one or two after the fix means either the fix regressed or something new is writing sandbox badges to the bucket.

**10:22 priya.raghunathan**
Good point. Threshold low, and I'll annotate the dashboard with "expected 0 post-CI-892" so whoever's on-call in August knows a blip is worth a look and isn't just noise.

**10:24 yusuf.adeyemi**
back, read it all, no objections from search — the two search-api ones are the same story, sandbox key, real-looking statement, wrong bucket, glad we're not paging. one thing for my own understanding: the worker rule keys off `key_id` in the attestation, right? not off the filename or the `_promoted/` folder? because filenames lie.

**10:25 ola.ferrand**
Correct, and that's the whole point of doing it in the worker. It reads `key_id` out of the signed statement inside the `atSt` chunk. The filename, the folder, the S3 metadata — none of that is in the trust decision. `badge-sbx-` could be renamed to `badge.png` tomorrow and the verdict would be identical, because the untrusted key is named inside the signed payload, not on the object. Filenames lie, signed statements don't.

**10:27 tomas.berg**
CI-892 is up for review, reverts the destination back to `northwind-sandbox-badges` and adds the README banner. Link: https://northwind.internal/ci/pipelines/sandbox-promote/CI-892. Kenji, you want to take the review since you know the promotion flow?

**10:28 kenji.watanabe**
On it. Also cleaning the six leaked objects out of the release bucket once the revert's merged, so the audit goes back to green:

```
$ aws s3 rm s3://northwind-release-badges/ --recursive \
    --exclude "*" --include "*/_promoted/badge-sbx-*.png" --dryrun
(dryrun) delete: s3://northwind-release-badges/payments-api/_promoted/badge-sbx-9f21a3c.png
(dryrun) delete: s3://northwind-release-badges/payments-api/_promoted/badge-sbx-1b77e04.png
(dryrun) delete: s3://northwind-release-badges/orders-api/_promoted/badge-sbx-2c0119d.png
(dryrun) delete: s3://northwind-release-badges/orders-api/_promoted/badge-sbx-6ae5f80.png
(dryrun) delete: s3://northwind-release-badges/search-api/_promoted/badge-sbx-40de8b1.png
(dryrun) delete: s3://northwind-release-badges/search-api/_promoted/badge-sbx-b3c2210.png
```

**10:29 kenji.watanabe**
Six, matches the audit. I'll run it for real after CI-892 merges, so we don't have the job re-writing them behind us while we delete.

**10:30 dana.whitfield**
Please leave one of them somewhere I can grab first. I want a copy of `badge-sbx-9f21a3c.png` as a fixture — a real release badge signed by the sandbox key with a valid signature is exactly the case I want in the worker's test set. It's the canonical "valid signature, untrusted key" example and I'd rather test against a real one than a synthesised one.

**10:31 kenji.watanabe**
Sure. I'll copy it to the fixtures stash before I delete from the release bucket. `fixtures/badges/` gets a sandbox-key case. It forces the worker to do the right thing in order: verify the signature (passes), apply the trust rule (fails), return `UNTRUSTED_KEY`. If anyone ever "optimises" the worker to short-circuit on a passing signature, this fixture catches it.

**10:36 dana.whitfield**
The one line I'd underline in blood before anyone leaves: valid signature, untrusted key, rejected. "Is it a bad signature?" — no. It never was. The bytes are fine. The signer isn't allowed to sign this. The sandbox key stays in the keyring because promotion needs it, and it may never sign a release badge; when it does, that badge is rejected as an untrusted key no matter which bucket it turned up in. Keep the signature question and the trust question apart and everything else in this room follows.

**10:37 tomas.berg**
Concur. CI-892 in review, README banner attached, will ping when it merges.

**10:38 ola.ferrand**
Concur. Worker returns `UNTRUSTED_KEY` for `k-ci-sandbox` on release badges, distinct from signature-failure verdicts, counter emitted per verdict, exercised by dana's fixture. Kenji's got the object cleanup and fixture copy after merge.

**10:39 ingrid.solberg**
Audit entry filed with the wording we agreed. Trust failure, not signature failure, control functioning. This is the kind of thread I like referencing later because the reasoning's in it, not just the outcome.

**10:41 marcus.lin**
Off PagerDuty, key stays, worker does the work. Good enough for me. Back to 8.4.1.

**10:42 priya.raghunathan**
Leaving the room open until CI-892 merges and the audit's green. Kenji drops the done, I'll close it. Good work everyone — and dana, the trust-vs-signature thing, can you stick that somewhere permanent? It comes up every quarter and we re-derive it every time. It should be written down once in a runbook.

**10:43 dana.whitfield**
I'll write it up in https://northwind.internal/runbooks/releasesentinel/trust-vs-validity. One page: "A valid signature is not trust. Trust is whether the key is allowed to make the claim. A badge can pass verification and still be rejected as an untrusted key." Sandbox-key case linked as the worked example.

**10:44 priya.raghunathan**
Perfect. Closing when the audit clears.
