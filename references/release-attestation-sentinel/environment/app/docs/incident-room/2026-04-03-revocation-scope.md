# #war-room-releasesentinel

## 2026-04-03

**07:41 priya.raghunathan**
Morning. Reconvening the war room. For anyone joining: last night we made the call that anything `k-legacy-2024` ever signed is untrusted, full stop. dana pulled an all-nighter on the forensics and says the picture changed. dana, floor is yours before I start fielding "is the release blocked" pings from every direction.

**07:42 priya.raghunathan**
Also: badge count that ReleaseSentinel rejected overnight is 0, because the worker rejected literally everything with `key_id":"k-legacy-2024"` per last night's config. So we don't have a data-loss situation, we have a "we may have over-blocked" situation. Which is the good kind of problem.

**07:44 dana.whitfield**
Ok. Long message incoming, bear with me, I want the reasoning on the record and not just the conclusion because we're going to reverse a decision we made at 1am and I want it to be reversible-with-evidence, not vibes.

**07:45 dana.whitfield**
Context for the record. The exposure: `k-legacy-2024` private material was in the `northwind-legacy-signing` bundle that got copied to the `build-scratch-share` S3 prefix during the migration cleanup. That copy is what leaked — a snapshot of that prefix ended up readable to a wider group than it should have been. That's the compromise. Last night we did not yet know *when* that copy could first have been used to sign anything, so we assumed the worst: treat every `k-legacy-2024` signature as attacker-controlled.

**07:46 dana.whitfield**
Overnight I had CloudTrail + the HSM audit export to actually answer the "when" question. And the "when" question is the whole ballgame, because if we can prove the exposed copy could not have produced a valid signature before a specific instant, then everything signed before that instant is exactly as trustworthy as it was two days ago.

**07:47 tomas.berg**
Before you go further — the legacy key is Ed25519 software key material, right, not sitting in the HSM? So what does the HSM audit log even tell us here.

**07:48 dana.whitfield**
Good, I should have led with that. Two artifacts, keep them straight:
1. The HSM audit log tells us when the *original* `k-legacy-2024` material was exported out of the HSM into the software bundle in the first place. That's the provenance of the copy.
2. CloudTrail tells us every read/copy against the `build-scratch-share` prefix — i.e. when the leaked snapshot could first have been in anyone's hands who wasn't supposed to have it.

**07:49 dana.whitfield**
The signature itself is done in software once you hold the material, so no, we don't get a "signing event" audit line the way you would for an HSM-resident key. That's exactly why last night felt so bad — we couldn't point at a log that says "attacker signed at time T". What we *can* do is bound it from the other side: prove the earliest instant the attacker could have possibly held usable key material, and then argue nothing before that is reachable.

**07:51 kenji.watanabe**
This is the argument I was trying to make at like 00:40 last night before priya sent everyone to bed. The blanket "everything it ever signed is dead" throws away the entire release history signed under that key for tags going back to early 2024. That's a lot of still-deployed stuff. I got told to stop being clever and go to sleep.

**07:51 priya.raghunathan**
You did get told that. In fairness it was 1am and "be conservative now, be precise in the morning" was the right call at 1am. It is now the morning. Be precise.

**07:53 dana.whitfield**
Right. Here's the HSM export line. This is when the legacy material left the HSM into the bundle:

```
2026-03-28T11:02:14Z  KMU-EXPORT  keyhandle=0x4c1a  label="k-legacy-2024"
   operator=svc-migration  wrapping=aes256-kwp  dest=northwind-legacy-signing.p12
   result=OK  audit_seq=889214
```

So the *bundle* has existed since 2026-03-28. That on its own doesn't hurt us — the bundle living in the HSM-adjacent secure store is fine, that's expected during a migration. What matters is when a copy of that bundle escaped into a place a non-operator could read it.

**07:55 dana.whitfield**
That's CloudTrail. The scratch-share prefix. Here's the copy-in and then the first read by a principal outside the migration service role:

```
# copy of the bundle INTO the wide-readable prefix
2026-04-02T17:30:00.000Z  s3:PutObject  bucket=northwind-build-scratch
   key=build-scratch-share/northwind-legacy-signing.p12
   principal=arn:aws:iam::…:role/svc-migration-cleanup
   sourceIP=10.42.6.11  requestID=B1F2…9A  result=200
```

**07:56 dana.whitfield**
That `PutObject` at `2026-04-02T17:30:00.000Z` is the moment the private material first landed somewhere it should not have. Before that instant the material existed only inside `svc-migration` scope and the HSM store. There is no CloudTrail evidence — none — of the bundle being readable outside that scope before `2026-04-02T17:30:00.000Z`.

**07:57 ola.ferrand**
So the exposure clock starts at 17:30:00.000Z yesterday. Not at the 03-28 export, not at some fuzzy "sometime in April". 17:30:00.000 on the dot, because that's the PutObject.

**07:58 dana.whitfield**
Correct. And to be thorough I went looking for the other side of it — is there any evidence of an *attacker* signature before that? Any anomalous badge, any statement with a weird `issued_at`, anything signed by legacy that we didn't expect. Answer: no. Every `k-legacy-2024` statement we have on record has an `issued_at` that lines up with a real release build we can independently account for, and the latest legitimate one predates yesterday afternoon comfortably. There is no evidence of any attacker signature before `2026-04-02T17:30:00.000Z`.

**08:00 priya.raghunathan**
Let me make sure I'm reading this the way you mean it. You're not saying "the key wasn't compromised". You're saying "the compromised *copy* did not and could not exist in attacker-reachable form until 17:30:00.000Z yesterday, therefore any signature that was produced before that instant was produced by us, legitimately."

**08:01 dana.whitfield**
That is exactly the claim. And it's the strongest form we can make it: it's not "we didn't see an attack", it's "the material required to mount the attack was not out of the box until 17:30:00.000Z".

**08:02 marcus.lin**
This matters a lot to payments. We've got production artifacts that were signed under legacy back before the current key existed and they're still the thing running. If the blanket revocation stands, ReleaseSentinel calls those untrusted and we can't re-verify a rollback badge if we ever need to roll back. So I'm very much in the "please walk it back" camp. But I don't want to be the guy pushing for the answer that's convenient for me — dana, is the evidence actually load-bearing or is it "probably fine"?

**08:03 dana.whitfield**
It's load-bearing. CloudTrail is the authoritative record for object access in that account, the trail was validated (log file integrity validation is on, digest chain intact for 04-01 through 04-03, I checked the digest files), and the PutObject is a hard event with a request ID. I'm not inferring the 17:30 boundary, I'm reading it off a tamper-evident log.

**08:04 kenji.watanabe**
Log file validation digest chain intact — can you drop the actual `aws cloudtrail validate-logs` tail in here so it's in the archive? Compliance is going to want it and ingrid's going to ask anyway.

**08:05 dana.whitfield**
```
$ aws cloudtrail validate-logs --trail-arn arn:aws:cloudtrail:…:trail/org-audit \
    --start-time 2026-04-01T00:00:00Z --end-time 2026-04-03T00:00:00Z
Validating log files for trail arn:aws:cloudtrail:…:trail/org-audit …
Results requested for 2026-04-01T00:00:00Z to 2026-04-03T00:00:00Z
Results found for 2026-04-01T06:00:00Z to 2026-04-03T00:00:00Z:
  3/3 digest files valid
  1188/1188 log files valid
```

**08:06 ingrid.solberg**
Thank you, that's the artifact I need. Noted for SEC-4471. Keep going, I have questions about the exact rule but I'll hold them until you've stated it.

**08:08 priya.raghunathan**
Ok so let's turn the evidence into the actual thing ReleaseSentinel enforces, because "the material wasn't out until 17:30" is a forensic finding, not a rule the worker can run. dana, what's the rule.

**08:10 dana.whitfield**
The rule keys off the statement's own `issued_at` field. Concretely: a statement signed by `k-legacy-2024` is still honoured **if and only if its `issued_at` is strictly before `2026-04-02T17:30:00.000Z`**. If the `issued_at` is at or after `2026-04-02T17:30:00.000Z`, ReleaseSentinel rejects it — treats `k-legacy-2024` as a revoked key for that statement.

**08:11 dana.whitfield**
So it's not "legacy key is dead" (last night) and it's not "legacy key is fine" (obviously not). It's: legacy key is trusted for anything it signed *before the exposure instant*, and revoked for anything dated at or after the exposure instant.

**08:12 tomas.berg**
And `issued_at` is the field inside the signed statement — so it's covered by the signature, an attacker can't backdate it without breaking the Ed25519 verification. That's the part that makes this safe, right? Otherwise "trust old timestamps" would be trivially forgeable.

**08:13 dana.whitfield**
Yes and that's the crux, thank you for saying it out loud. `issued_at` is inside `statement`, and the signature is over the whole statement. To forge a pre-17:30 statement the attacker needs a valid signature over a statement whose `issued_at` reads e.g. `2026-03-15T…`. They can only make a valid signature with the key material, which they didn't have until 17:30 yesterday. So they cannot produce a validly-signed statement with a pre-17:30 `issued_at`. The timestamp being *inside* the signed blob is exactly what lets us trust it.

**08:14 ola.ferrand**
Right, if `issued_at` were metadata on the PNG chunk instead of inside the signed statement, this whole rule would be worthless because you'd just edit the chunk. It's in the statement. Good.

**08:15 marcus.lin**
This unblocks payments' rollback-verification concern completely. Everything we care about was issued months ago, all comfortably before yesterday afternoon. Thank you. I'll stop being the loud one now.

**08:16 kenji.watanabe**
For the record the thing that was signed most recently under legacy that I can find is a `v8.2.1` rebuild badge, `issued_at` `2026-02-19T08:41:00.000Z`. Miles before the boundary. Nothing legitimate is anywhere near 17:30 yesterday, which is consistent with dana's "the latest legit one predates yesterday comfortably".

**08:18 ingrid.solberg**
Ok. Now my questions, and I need these nailed down precisely because "before" in English is ambiguous and I am the person who has to write the exact wording into the control document. I want to drill the boundary.

**08:18 ingrid.solberg**
Question one. A statement signed by `k-legacy-2024` with `issued_at` = `2026-04-02T17:29:59.999Z`. One millisecond before. Honoured or rejected?

**08:19 dana.whitfield**
Honoured. It's strictly before `2026-04-02T17:30:00.000Z`, so it's on the trusted side. That timestamp is before the PutObject, the material wasn't out yet, we trust it.

**08:19 ingrid.solberg**
Question two, the one I actually care about. A statement with `issued_at` = **exactly** `2026-04-02T17:30:00.000Z`. The same instant as the PutObject, to the millisecond. Honoured or rejected?

**08:20 dana.whitfield**
Rejected.

**08:20 ingrid.solberg**
State it as a rule, not a one-word answer, because a one-word answer is how these things get implemented wrong six months later.

**08:21 dana.whitfield**
The cutoff is inclusive on the reject side. The rule is: honoured iff `issued_at < 2026-04-02T17:30:00.000Z` (strict less-than). Rejected iff `issued_at >= 2026-04-02T17:30:00.000Z` (greater-than-or-equal). Therefore `issued_at == 2026-04-02T17:30:00.000Z` exactly falls under `>=`, and is **rejected**. Equality goes to reject. There is no honoured statement whose `issued_at` equals the boundary instant.

**08:22 ingrid.solberg**
That's what I needed. So to say it back in my own words for the control doc: the boundary instant `2026-04-02T17:30:00.000Z` itself is *not* a trusted instant. Trust requires being genuinely earlier than it. At the boundary and beyond, revoked.

**08:22 dana.whitfield**
Correct in every particular.

**08:23 kenji.watanabe**
And that's the defensible choice too, not just an arbitrary tie-break. The PutObject *happened at* 17:30:00.000Z. We can't prove the material was still contained at the exact instant it was being copied out — that instant is the escape. Anything stamped at that instant or later is inside the window of possible compromise. So inclusive-on-reject isn't us being fussy, it lines up with the physical event.

**08:24 ola.ferrand**
I like that the boundary logic matches the evidence. `>=` on the reject side because the escape event itself is `2026-04-02T17:30:00.000Z` and you don't get to claim the instant of the leak as a safe instant. Clean.

**08:25 ingrid.solberg**
One more edge, sorry, I have to. What if a statement has `issued_at` that is missing, malformed, or in a timezone offset that isn't `Z`? Does the comparison even happen?

**08:26 dana.whitfield**
That's genuinely out of scope for *this* decision and I don't want to muddy the revocation rule with parsing behaviour — the revocation rule assumes you already have a well-formed UTC `issued_at` from a statement whose signature already verified. If the statement doesn't verify or `issued_at` won't parse, you never reach the legacy-key revocation check, it's rejected for the earlier reason. The rule we're setting today is purely: given a validly-signed `k-legacy-2024` statement with a parseable UTC `issued_at`, compare against `2026-04-02T17:30:00.000Z`, strict-less-than trusted, `>=` rejected.

**08:26 ingrid.solberg**
Accepted. That's a clean scope boundary and I'll write it that way — the revocation comparison presupposes a verified, parseable statement.

**08:28 priya.raghunathan**
Ok. This is a reversal of an active production config, so I'm not merging it on my own authority. ruth, you're the only one who can bless this. Have you been reading along or do you need the two-line version.

**08:29 ruth.callahan**
I've read the whole thing. Let me restate it back so my sign-off is unambiguous and can't be misquoted later.

**08:30 ruth.callahan**
Last night's decision — every statement ever signed by `k-legacy-2024` is untrusted — is **reversed**, effective now. It is replaced by a time-scoped rule based on the statement's signed `issued_at` field:

**08:30 ruth.callahan**
A statement signed by `k-legacy-2024` is honoured if and only if its `issued_at` is strictly before `2026-04-02T17:30:00.000Z`. A statement whose `issued_at` is at or after `2026-04-02T17:30:00.000Z` — the boundary instant itself included — is rejected, the key treated as revoked for that statement. This is grounded in dana's forensics: CloudTrail shows the private material first became reachable outside `svc-migration` at the `PutObject` at `2026-04-02T17:30:00.000Z`, and there is no evidence of any attacker signature before that instant.

**08:31 ruth.callahan**
I'm signing off on that. Recorded against SEC-4471. dana's CloudTrail validation output and the HSM export line are the evidence of record. kenji — you called this correctly last night and got sent to bed for it, noted and appreciated.

**08:32 kenji.watanabe**
Appreciated. No hard feelings, it genuinely was the right call to over-block at 1am with no forensics in hand.

**08:32 priya.raghunathan**
Signed off by ruth. That's the authority. tomas, dana — get the config change staged so the worker stops rejecting the whole legacy history. I want the reject set to shrink from "all legacy" to "legacy issued_at >= 17:30 yesterday".

**08:33 dana.whitfield**
On it. Just to be crystal clear for whoever implements: the comparison instant is `2026-04-02T17:30:00.000Z`, strict-less-than is the honoured side, `>=` is the rejected side, equality rejects. Don't "round" the boundary, don't use `<=` on the honoured side, don't drop the milliseconds.

**08:34 tomas.berg**
Milliseconds preserved. `.000Z` is part of the instant, I'm treating `2026-04-02T17:30:00.000Z` as the literal comparison value, not `2026-04-02T17:30Z`. Filing REL-3390 for the config change and linking SEC-4471.

**08:35 ola.ferrand**
And since `issued_at` values in real badges carry milliseconds too (they're all `…:00.000Z` style), the comparison is millisecond-resolution on both sides. A badge at `…17:29:59.999Z` is honoured, `…17:30:00.000Z` is rejected, one millisecond apart. That's the resolution we're operating at.

**08:36 ingrid.solberg**
Confirmed, and that millisecond gap is exactly why I made everyone stare at the boundary. The control doc will read: "trusted iff issued_at < 2026-04-02T17:30:00.000Z (UTC, millisecond precision); at or after that instant, revoked." Word for word.

**08:41 yusuf.adeyemi**
oh no I slept through the whole thing. reading up now. ok so the tldr is we un-blanket-banned the legacy key and it's time-scoped now. so anything before April is fine? and April-onwards is revoked?

**08:42 kenji.watanabe**
No. Please don't write "before April" anywhere, that's wrong in a way that matters.

**08:42 kenji.watanabe**
The boundary is not "April" and it's not a date, it's a specific *instant*: `2026-04-02T17:30:00.000Z`. So a `k-legacy-2024` statement issued on, say, `2026-04-02T09:00:00.000Z` — that's April, but it's the morning of the 2nd, before 17:30 — is **honoured**, not rejected. "Before April is fine" would wrongly reject the entire first seventeen and a half days of April that are actually trusted. The line is 17:30:00.000Z on 2026-04-02, not "the start of April".

**08:43 dana.whitfield**
Right. yusuf, the mental model is not month-based. It's: was this statement signed before the private key leaked (before `2026-04-02T17:30:00.000Z`) → trusted; at-or-after the leak → revoked. Plenty of trusted statements were issued in April. Plenty could even be issued at 17:29 yesterday and still be fine.

**08:43 yusuf.adeyemi**
ahh ok. so it's not "April = bad", it's "before 17:30:00.000Z on the 2nd = good, from that instant on = bad", and the 17:30 is because that's when dana's cloudtrail shows the key material actually leaked. got it. sorry, "before April" was me pattern-matching lazily.

**08:44 kenji.watanabe**
Exactly that. And the "from that instant on" is inclusive — 17:30:00.000Z itself is on the bad side. But yes you've got the shape of it now.

**08:44 yusuf.adeyemi**
inclusive at the instant, noted. so if I somehow had a legacy badge stamped exactly 17:30:00.000Z it's rejected, and 17:29:59.999Z it's honoured. ok. thanks for un-lazy-ing me.

**08:45 dana.whitfield**
Perfect, that's the rule, you've got it exactly.

**08:47 marcus.lin**
Can we sanity-check against a real badge so this isn't purely theoretical? Here's one payments cares about, pulled from the artifact store, the `v8.2.1` legacy-signed one kenji mentioned:

```json
{"signature":"iQEzBAABCgAd…8f2a==",
 "statement":{"artifact_digest":"sha256:9f4c1b…",
              "issued_at":"2026-02-19T08:41:00.000Z",
              "key_id":"k-legacy-2024",
              "release_branch":"release/8.2",
              "release_tag":"v8.2.1",
              "service":"payments-api"}}
```

`issued_at` `2026-02-19T08:41:00.000Z` < `2026-04-02T17:30:00.000Z`. So under the new rule ReleaseSentinel honours it. Under last night's rule it rejected it. That's the exact regression we're fixing.

**08:48 dana.whitfield**
Correct — honoured. February, strictly before the boundary, valid signature, `key_id` is legacy but that's fine because it's pre-exposure. That's the case working as intended.

**08:48 tomas.berg**
And to construct the mirror-image reject case, purely hypothetically since we don't actually have a legit one this late: a statement with `key_id":"k-legacy-2024"` and `issued_at":"2026-04-02T18:00:00.000Z"` — half an hour after the leak — would be rejected. If such a badge exists at all it's suspect by definition, because we have no legitimate reason to have signed anything with legacy at 18:00 yesterday, and the material was out by then.

**08:49 dana.whitfield**
Right, and that's the reassuring part — the honoured set is entirely historical legitimate builds, and the rejected set is "things dated into the exposure window", which for legacy should be empty of legitimate artifacts anyway. We're not cutting off anything real; we're closing the door on anything an attacker could mint from 17:30 onward.

**08:52 priya.raghunathan**
Alright. Where we are: reversal is approved by ruth, evidence is dana's CloudTrail (validated) + HSM export, rule is `issued_at` strict-less-than `2026-04-02T17:30:00.000Z` honoured / `>=` rejected with equality rejecting, config change is REL-3390, control doc is SEC-4471. tomas is staging. Anything blocking before I downgrade this from war room to a normal follow-up?

**08:53 ingrid.solberg**
Nothing blocking from compliance. I have the boundary wording and the validation artifact. I'll want the final merged config diff attached to SEC-4471 when REL-3390 lands but that doesn't block closing the room.

**08:54 dana.whitfield**
Nothing blocking from security. I'll leave the two log excerpts pinned in this thread so the "why 17:30:00.000Z" question never has to be re-litigated. If anyone reopens this, the answer is: that's the PutObject instant, it's in the tamper-evident trail, full stop.

**08:54 kenji.watanabe**
Nothing from me. Rule's clear and I've verified it does the right thing on the one real legacy badge we all care about.

**08:55 marcus.lin**
Payments is happy. Rollback verification unblocked. Thanks all, and sorry for being the loud "walk it back" voice at 8am, turns out the loud voice was right for once but only because dana did the actual work.

**08:55 ola.ferrand**
The extractor's been noisy all night on some legacy badges by the way — a couple of them the worker chewed on for a while and spat garbage before it even got to the signature check. Different problem, not touching it in this thread, just flagging so nobody thinks the revocation rule caused it. Still don't know why it does that. Separate ticket.

**08:56 priya.raghunathan**
Noted and explicitly out of scope here — the crash thing is its own gremlin, keep it out of the revocation record. This thread is the revocation rule and nothing else.

**08:57 yusuf.adeyemi**
one more from me so I don't misremember it later: the rule is about the `issued_at` inside the signed statement, not when ReleaseSentinel *sees* the badge or when the file landed on disk, right? like if a pre-17:30 badge shows up in the store tomorrow it's still honoured?

**08:58 dana.whitfield**
Correct. It's the `issued_at` in the statement, full stop — not ingest time, not file mtime, not verification time. A badge with a pre-`2026-04-02T17:30:00.000Z` `issued_at` is honoured whenever ReleaseSentinel encounters it, today, tomorrow, next year. The instant that matters is the one the signer committed to inside the signed blob.

**08:58 yusuf.adeyemi**
great. signed statement's issued_at vs 2026-04-02T17:30:00.000Z. that's the whole rule. thanks.

**08:59 ingrid.solberg**
And because it's the signed `issued_at`, it's stable and auditable forever — the trust decision for any given legacy badge never changes over time, it's a pure function of a value baked into the signature. That's the property I'll be citing in the control. Good.

**09:00 ruth.callahan**
Confirmed and closed on my side. To restate the reversal one final time for the record so there is exactly one authoritative sentence: as of 2026-04-03, `k-legacy-2024` is trusted for statements whose signed `issued_at` is strictly before `2026-04-02T17:30:00.000Z`, and revoked for statements whose `issued_at` is at or after `2026-04-02T17:30:00.000Z` (the boundary instant inclusive on the revoked side). This supersedes last night's blanket revocation. SEC-4471 owns the record.

**09:01 priya.raghunathan**
Thank you all. Downgrading the room. tomas, ping me when REL-3390 is staged and I'll get it reviewed. dana, get some sleep. kenji, also get some sleep, you earned the "I told you so" but I need you awake later.

**09:02 kenji.watanabe**
Taking the sleep. Leaving the "I told you so" on the table for a rainy day.

**09:02 tomas.berg**
REL-3390 staged in ~20, will ping. Boundary literal is `2026-04-02T17:30:00.000Z`, honoured side strict `<`, rejected side `>=`. It's in the change description verbatim so nobody re-derives it wrong.

**09:03 dana.whitfield**
Perfect. Pinning the two log lines now and signing off. For the record one last time so it's next to the pins: no evidence of any attacker signature before `2026-04-02T17:30:00.000Z`; that instant is the CloudTrail PutObject; trust is strictly-before, revoke is at-or-after. Done.
