# #war-room-releasesentinel — 2026-04-27

## 2026-04-27

**08:41 dana.whitfield**
Morning. Today we finally do the annual build-key rotation. Filing this here because I want the whole conversation in one searchable place, not scattered across DMs and a ticket comment nobody can find later.

**08:41 dana.whitfield**
Short version, then we argue: `k-build-2026a` is already live and signing real releases. As of this rotation it becomes the *sole* production build key. `k-build-2025b`, the production build key for the last year, gets retired. Ticket is SEC-2291.

**08:42 priya.raghunathan**
Define "retired". I need an exact word and an exact instant, not a vibe. Last rotation we said "end of April" and I spent two days fielding pages because it meant different things to different pipelines.

**08:43 dana.whitfield**
That's exactly why I want it nailed down in writing before anyone touches anything. Give me a minute.

**08:47 dana.whitfield**
Proposal. `k-build-2025b` is retired at a single hard cutover instant: **2026-05-01T00:00:00.000Z**. Not "May 1st", not "end of April" — the instant `2026-05-01T00:00:00.000Z`, UTC, to the millisecond. The rule ReleaseSentinel applies is about the statement's `issued_at`, not when the worker evaluates the badge:

- A statement signed by `k-build-2025b` whose `issued_at` is **strictly before** `2026-05-01T00:00:00.000Z` stays valid and trusted. Forever. That badge is not compromised, it's just old. Every release we cut in the last year keeps verifying exactly as it does today.
- A statement signed by `k-build-2025b` whose `issued_at` is **at or after** `2026-05-01T00:00:00.000Z` is rejected. That key is retired, and anything it signs from the cutover onward is treated as a revoked/retired key signing.

**08:48 priya.raghunathan**
So it's an expiry, not a revocation.

**08:49 dana.whitfield**
For everything before `2026-05-01T00:00:00.000Z`, yes — expiry, full stop. The key did its job, it aged out, the signatures it already produced are fine. I will die on this hill: retiring `k-build-2025b` is NOT declaring it compromised. Nobody stole it. We are rotating on schedule. Historical badges must keep working, because we verify old artifacts all the time — rollbacks, forensic checks, compliance re-scans.

**08:50 ingrid.solberg**
From compliance, I want the wording precise, because "retired" and "revoked" have very different meanings in our attestation register. Are we recording this as an expiry event or a revocation event? They file differently.

**08:51 dana.whitfield**
Expiry event. `k-build-2025b` reaches end-of-life at `2026-05-01T00:00:00.000Z`. There is no compromise, no incident, no breach. The register entry should say the key was rotated out on schedule, effective `2026-05-01T00:00:00.000Z`, and that statements it signed before that instant remain valid.

**08:52 ingrid.solberg**
Thank you. I'll draft the register entry against that exact instant and paste it back here before I file it.

**08:53 tomas.berg**
Wait. Before we carve `2026-05-01T00:00:00.000Z` into stone — can we talk about the cutover being *hard*? Half of release engineering's pipelines don't pick up a new signing key the moment we flip a config. The key material propagates through our secrets sync, and that sync is slow — some runners only refresh their key cache on the next scheduled build, which for quieter services can be days apart. If we hard-cut at `2026-05-01T00:00:00.000Z`, any pipeline that hasn't rolled over to `k-build-2026a` by then keeps signing with `k-build-2025b`, and those badges bounce.

**08:54 tomas.berg**
Give us a grace period. Two weeks. Let `k-build-2025b` keep signing valid releases through, say, `2026-05-15`, so slow pipelines have time to catch up. Then hard-cut. That's all I'm asking.

**08:55 dana.whitfield**
No.

**08:55 dana.whitfield**
And I'll explain why, because I don't want it to sound like a reflex. A grace period defeats the entire point of a rotation. The whole reason we rotate is to establish that after a fixed instant, only the current production key `k-build-2026a` is authorized to sign new releases. If we let `k-build-2025b` keep signing *new* statements — `issued_at` after the cutover — for another two weeks, then for those two weeks we effectively have two live production build keys and no clean line between them. The cutover instant stops meaning anything.

**08:57 tomas.berg**
I'm not asking for fuzzy, just a later number.

**08:58 dana.whitfield**
The number isn't the issue, the meaning is. If I move the retirement of `k-build-2025b` to `2026-05-15`, then it's a production key until `2026-05-15`, and I've quietly extended the life of the *old* key by two weeks to paper over the fact that some pipelines are slow. That's rewarding the slow pipelines by weakening the rotation. The fix for "our pipelines are slow to pick up new keys" is to make the pipelines pick up the new key, not to keep the old key alive.

**09:00 priya.raghunathan**
yusuf, you around? this is about you

**09:03 yusuf.adeyemi**
half around, in another meeting. what did I do

**09:03 priya.raghunathan**
nothing yet. tomas is worried search-api's slow build cadence means you'll still be signing with `k-build-2025b` after it retires. when does search-api next cut a release?

**09:05 yusuf.adeyemi**
uh. we cut v8.5.0 last week off release/8.5, next scheduled build isn't until the 6th of May. but we can force a build any time. if the ask is "make sure search-api is signing with `k-build-2026a` before `2026-05-01T00:00:00.000Z`" then just tell me and I'll trigger a rollover build this week. ten minute job.

**09:06 dana.whitfield**
That is exactly the ask, and the whole answer to tomas's concern — you don't need a grace period, you need to roll the pipeline over before the instant, and it's a ten minute job.

**09:07 tomas.berg**
search-api can force a build in ten minutes. Not every pipeline can — some are behind change windows.

**09:08 dana.whitfield**
Then those pipelines get scheduled into a change window before `2026-05-01T00:00:00.000Z`. We have four days. This rotation has been on the calendar since February — it's in the schedule at https://northwind.internal/runbooks/build-key-rotation and the date has not moved.

**09:09 ruth.callahan**
Reading up. I'm going to back dana and close the grace-period question so we can get on with the work.

**09:10 ruth.callahan**
tomas, I hear the operational pain and it's real, but a grace period on a signing-key retirement is a security director's nightmare and I'm not signing off on one. The rotation instant is `2026-05-01T00:00:00.000Z` and it's hard. `k-build-2025b` does not sign a single valid *new* release after that instant. If a pipeline can't roll over in time, the answer is to roll it over faster or accept that its next build is rejected until it's on `k-build-2026a` — not to weaken the cutover for everyone. This is the kind of thing a grace period turns into a permanent fixture. "Just two weeks" becomes "just until next quarter" becomes an old key that never dies. No.

**09:11 tomas.berg**
Understood. On the record: I think we'll eat at least one avoidable rejected build over this. But it's your call and I'll stop pushing.

**09:12 ruth.callahan**
Noted, and I'd rather eat one rejected build than blur the line. Let's make it zero. dana owns the keyring side, tomas owns getting pipelines onto `k-build-2026a`, priya runs rollout tracking.

**09:13 priya.raghunathan**
Works. So the decision, so nobody has to scroll: `k-build-2025b` retires at `2026-05-01T00:00:00.000Z`, hard, no grace period. Before that instant its signatures are valid (expiry, not compromise). At or after that instant, rejected.

**09:13 dana.whitfield**
That's it. And to be explicit about the boundary because boundary bugs are the ones that bite: `issued_at` of exactly `2026-05-01T00:00:00.000Z` is *at* the cutover, so a `k-build-2025b` signature at exactly that instant is rejected. Strictly-before is trusted. The instant itself falls on the rejected side.

**09:14 kenji.watanabe**
So the trusted set is the half-open range `[past, 2026-05-01T00:00:00.000Z)`. Valid for `issued_at < 2026-05-01T00:00:00.000Z`, rejected for `issued_at >= 2026-05-01T00:00:00.000Z`.

**09:16 marcus.lin**
Dropping in because payments-api cares. Confirm I'm not about to break anything: all our shipped payments-api badges — v8.4.0, v8.4.1, the whole back catalogue, signed by `k-build-2025b` — keep verifying, right? Because I don't have the bandwidth this quarter to re-sign a year of releases.

**09:17 dana.whitfield**
They keep verifying, and you don't re-sign anything. Nobody does. Every one was signed with `issued_at` well before `2026-05-01T00:00:00.000Z`, so they're on the trusted side of the boundary and nothing about this rotation touches them. That's the point of an expiry-not-compromise retirement — and the entire reason we keep `k-build-2025b`'s public key in the keyring, which I want to make explicit.

**09:20 dana.whitfield**
Keyring point, important, want it explicit so nobody "helpfully" cleans it up in six months: **`k-build-2025b`'s public key STAYS in `/app/config/keyring.json`.** We are retiring the key as a *signer of new releases*. We are not removing its public key material. If we pull the public key, ReleaseSentinel can no longer verify the Ed25519 signature on any of the thousands of historical badges it signed, and every one of them flips from "trusted" to "can't even check". That would be self-inflicted.

**09:21 dana.whitfield**
So: public key stays. The keyring, as ever, carries public key material only — it says nothing about whether a key is allowed to sign. It'll hold `k-build-2025b`'s public key long after `2026-05-01T00:00:00.000Z`, and that's correct, because verification of old signatures needs it.

**09:22 kenji.watanabe**
The recurring gotcha with our keyring. Presence in `keyring.json` means "we can verify a signature made by this key", it does NOT mean "this key is authorized to sign a new release". Two different questions and the file only answers the first. So `k-build-2025b` after `2026-05-01T00:00:00.000Z`: keyring can still verify the signature is valid, but policy rejects the statement because a retired key signed it after its retirement instant.

**09:24 ola.ferrand**
Late, caught up. One clarification for the worker side, since I own the thing that evaluates this. The rejection at/after the cutover — that's a *policy* rejection, right? The signature still verifies cryptographically, we just refuse to trust the statement. I want us logging "rejected: signing key retired" and not "signature invalid", because those are very different alarms and I don't want anyone chasing a phantom key compromise.

**09:25 dana.whitfield**
Yes. Policy rejection, not a crypto failure. The signature made by `k-build-2025b` is genuine and verifiable. We reject the *statement* because the key that made it was retired as of `2026-05-01T00:00:00.000Z` and the `issued_at` is at or after that. The log line makes it unambiguous this is a retirement decision, so nobody wakes up thinking the key leaked.

**09:27 yusuf.adeyemi**
back for real now. someone said the word "legacy" earlier while I was half-listening and I panicked. does this rotation change anything for `k-legacy-2024`? do I need to worry about that one too while I'm rolling search-api over?

**09:28 dana.whitfield**
No. `k-legacy-2024` is a completely separate matter and this rotation does not touch it in any way. Whatever the rule is for `k-legacy-2024`, it is unchanged by today's work and it lives in its own thread. I'm not going to re-derive it here because that just risks me stating it slightly wrong and confusing the record. Today is about `k-build-2025b` retiring and `k-build-2026a` becoming the sole production build key. Full stop.

**09:29 yusuf.adeyemi**
got it, legacy is not my problem today.

**09:29 kenji.watanabe**
+1 on not re-deriving it here. Every time someone summarizes another key's rule from memory it ends up subtly wrong and people cite the wrong version. Leave `k-legacy-2024` where it lives.

**09:33 priya.raghunathan**
OK. Runbook. dana, walk me through the keyring-side steps so I can put them on the checklist and we start ticking boxes. Ordered, not prose.

**09:36 dana.whitfield**
Rotation runbook, keyring + policy side. Going onto https://northwind.internal/runbooks/build-key-rotation as the 2026a revision. Ordered:

1. Confirm `k-build-2026a` public key is present and correct in `/app/config/keyring.json`. It went in during the pre-stage in March (SEC-2210). Verify the fingerprint against the HSM export before we rely on it as the sole key. Do NOT skip the fingerprint check.
2. Confirm `k-build-2026a` is already producing real signed releases in staging that ReleaseSentinel trusts today. It is — payments-api staging has signed with `k-build-2026a` for two weeks. We never retire the old key before the new one is proven.
3. Confirm `k-build-2025b` public key REMAINS in `/app/config/keyring.json`. A no-op step that exists specifically to stop someone deleting it. Historical verification depends on it. Explicit affirmative tick, not an assumption.
4. Record the retirement instant: `k-build-2025b` retired effective `2026-05-01T00:00:00.000Z`. `issued_at` strictly before → trusted (expiry). `issued_at` at or after → rejected (retired key).
5. Coordinate with release engineering (tomas) so every production pipeline is signing with `k-build-2026a` and has stopped requesting `k-build-2025b` before `2026-05-01T00:00:00.000Z`. Rollout tracking owned by priya.
6. File the compliance register entry (ingrid) as an *expiry* event, effective `2026-05-01T00:00:00.000Z`, explicitly noting no compromise.
7. After `2026-05-01T00:00:00.000Z`: monitor for any badge signed by `k-build-2025b` with `issued_at >= 2026-05-01T00:00:00.000Z`. Each is a pipeline that missed the rollover, and it'll be rejected. Chase it, don't weaken the rule.

**09:38 tomas.berg**
Let me lay out the release-engineering side, the pipeline rollover half, since dana did the keyring half. Per production pipeline:

1. Point the pipeline's signing config at `k-build-2026a` — the `BUILD_SIGNING_KEY_ID` in the release pipeline template, flip it from `k-build-2025b`.
2. Force the runner to refresh its key cache. The slow part. Either wait for the scheduled build or trigger a manual rollover build. For anything with a build cadence longer than four days between now and the cutover, we MUST trigger a manual rollover build, because "wait for the scheduled build" won't land before `2026-05-01T00:00:00.000Z`.
3. Cut a throwaway rollover build, confirm the badge has `key_id: k-build-2026a`, verify ReleaseSentinel trusts it, mark the pipeline green.

**09:41 tomas.berg**
The pipelines I already know are on a long cadence and need a manual rollover build this week: search-api weekly (yusuf's on it), orders-api nightly (kenji, do a manual one to be safe), payments-api is already on 2026a in prod as of yesterday's build. The one I'm nervous about is the data-exports pipeline — not owned by anyone in this room, builds maybe twice a month.

**09:42 priya.raghunathan**
Dashboards. Setting up two so we can watch this without asking each other constantly.

**09:43 priya.raghunathan**
Rollout dashboard: https://northwind.internal/dash/key-rotation-2026a — one row per production pipeline, columns: current signing `key_id`, last build time, last badge `key_id`, rollover status (red = still 2025b, amber = flipped config but no build yet, green = built a 2026a badge and ReleaseSentinel trusts it). Goal is all-green before `2026-05-01T00:00:00.000Z`.

**09:43 priya.raghunathan**
Rejection watch dashboard: https://northwind.internal/dash/sentinel-rejections — post-cutover, counts any badge ReleaseSentinel rejects with reason "signing key retired" and `key_id` of `k-build-2025b`. Before the cutover this should be flat zero. After, any spike is a pipeline that missed the memo.

**09:44 priya.raghunathan**
Current state of the rollout dashboard: payments-api green, orders-api amber (config flipped, kenji doing a manual build), search-api red (yusuf about to trigger), data-exports red and greyed because nobody's claimed it, three internal tooling pipelines green. So the two reds are search-api and data-exports.

**09:45 yusuf.adeyemi**
triggering search-api rollover now. https://northwind.internal/ci/search-api/builds/40817 will tell us. ~8 min.

**09:46 kenji.watanabe**
orders-api manual build kicked off too, https://northwind.internal/ci/orders-api/builds/91120. Flipped `BUILD_SIGNING_KEY_ID` to `k-build-2026a` in the template at 09:40.

**09:52 kenji.watanabe**
orders-api build 91120 done. Badge statement:
```json
{"statement":{"artifact_digest":"sha256:2b9f...c41d","issued_at":"2026-04-27T09:51:07.000Z","key_id":"k-build-2026a","release_branch":"release/8.5","release_tag":"v8.5.0-rollover.1","service":"orders-api"}}
```
`key_id: k-build-2026a`, ReleaseSentinel trusts it. orders-api is green. Two reds left: search-api (in flight) and data-exports (orphan).

**09:55 yusuf.adeyemi**
search-api build 40817 green. badge `key_id` is `k-build-2026a`, `issued_at` 2026-04-27T09:54:41.000Z, trusted. search-api is green. told you, ten minutes. tomas you can stop worrying about my service.

**09:56 tomas.berg**
About your service, yes. About data-exports, no.

**09:58 tomas.berg**
So here's the "team that misses the memo" I was afraid of. data-exports is run by the analytics platform team. Not in this channel, not on the February rotation planning thread, and I'd bet money they don't know today is rotation day. Their pipeline builds roughly the 1st and 15th of the month. Guess what date their next build lands on.

**09:59 priya.raghunathan**
The 1st.

**09:59 tomas.berg**
The 1st. Their monthly build almost certainly fires early on `2026-05-01`, after the cutover, and if their runner hasn't refreshed its key cache it signs with `k-build-2025b` and gets rejected. That's the avoidable rejected build I said we'd eat.

**10:00 dana.whitfield**
Then let's not eat it. Who owns analytics platform? Page them. This is exactly the case runbook step 5 exists for — a pipeline that needs rolling over before `2026-05-01T00:00:00.000Z` and doesn't know it.

**10:04 priya.raghunathan**
Paged analytics-platform on-call via https://northwind.internal/oncall/analytics-platform. Got a human, they had no idea. Confirmed: data-exports still has `BUILD_SIGNING_KEY_ID = k-build-2025b`, next scheduled build `2026-05-01T06:00` local. Which brings us neatly to the timezone landmine.

**10:05 kenji.watanabe**
`2026-05-01T06:00` *local* is doing a lot of work in that sentence. Local where?

**10:05 priya.raghunathan**
The analytics on-call said "6am on the 1st, so we're after your midnight cutover by six hours, we're fine, we'll roll over on the 2nd". I don't think that's right but check my head.

**10:06 dana.whitfield**
That's wrong, and it's wrong in the dangerous direction. The cutover is `2026-05-01T00:00:00.000Z`. Their build runners are in Central European Time, which on `2026-05-01` is UTC+2 (daylight time). So their "6am local" build is `2026-05-01T06:00+02:00` = `2026-05-01T04:00:00.000Z`. That is four hours *after* the cutover, not fine. Any badge that build produces with `key_id: k-build-2025b` has `issued_at` at or after `2026-05-01T00:00:00.000Z` and gets rejected.

**10:07 kenji.watanabe**
And the on-call's framing gave it away — "after your midnight cutover by six hours" assumes the cutover is *their* midnight. It's not. `2026-05-01T00:00:00.000Z` is `2026-05-01T02:00` local CET. By the time their clock says midnight on the 1st, the cutover already happened two hours earlier. Their "6am local" is well past it.

**10:09 dana.whitfield**
This is exactly why the policy instant is quoted in UTC to the millisecond and nowhere in the runbook does it say "May 1st" unqualified. `2026-05-01T00:00:00.000Z`. Everyone converts from that. The moment someone reasons in local time about a global cutover, someone builds four hours late and gets rejected.

**10:10 ingrid.solberg**
For the audit note I'll add a sentence, because an auditor will ask: "the retirement instant is `2026-05-01T00:00:00.000Z` (UTC); local-time interpretations do not apply; `issued_at` values in badge statements are recorded in UTC and compared against this instant directly." Reads correctly to security?

**10:11 dana.whitfield**
Reads correctly. `issued_at` is always UTC with the `Z` suffix — e.g. `"issued_at":"2026-05-12T09:14:00.000Z"`. So the comparison is UTC-to-UTC, no conversion, no ambiguity. The only place local time entered was in a human's head, and it was wrong.

**10:12 priya.raghunathan**
So the action for analytics platform: roll data-exports over to `k-build-2026a` NOW, don't wait for the `2026-05-01` scheduled build. Told the on-call, they're flipping config and triggering a manual rollover build. And I'm widening the memo — data-exports missed it because the announcement only went to release-eng and security. Reposting the notice (instant `2026-05-01T00:00:00.000Z`, hard cutover, roll over before then) to #eng-announce and #platform-all so no other orphan gets surprised. Should've done that in February.

**10:14 tomas.berg**
Should've. But at least we caught data-exports with four days to spare instead of finding out from the rejection dashboard on May 1st.

**10:31 priya.raghunathan**
data-exports build 2051 green, badge `key_id: k-build-2026a`, `issued_at 2026-04-27T10:29:52.000Z`, trusted. data-exports is GREEN. Rollout dashboard is now all-green. Every production pipeline is signing with `k-build-2026a` and none will sign a new statement with `k-build-2025b`.

**10:32 dana.whitfield**
That's the outcome that makes the hard cutover painless. All-green four days before `2026-05-01T00:00:00.000Z`. tomas, your one-rejected-build prediction is looking beatable.

**10:33 tomas.berg**
I'll happily be wrong. Leaving my "we might eat one" on the record — there's still a long tail of pipelines I don't know about.

**10:34 marcus.lin**
Question from the payments side, on the record so I don't get asked later. A badge we ALREADY shipped, signed by `k-build-2025b`, `issued_at` say `2026-03-10` — after `2026-05-01T00:00:00.000Z` passes, when a customer re-verifies that badge in July, ReleaseSentinel still trusts it, yes? The cutover is about `issued_at`, not about when verification happens.

**10:35 dana.whitfield**
Yes, still trusted in July, still trusted in 2030. The comparison is `issued_at` versus `2026-05-01T00:00:00.000Z`. A March `issued_at` is strictly before the cutover, so it's on the trusted side permanently. It does not matter that *verification* happens after the cutover — we evaluate the statement's `issued_at`, not the wall clock at verification time. Old badges: fine forever. New badges from the old key: rejected.

**10:37 kenji.watanabe**
Worth one concrete example set for the runbook, zero ambiguity, using `k-build-2025b` signatures:
- `issued_at 2026-04-30T23:59:59.999Z` → strictly before → **trusted** (expiry, historical).
- `issued_at 2026-05-01T00:00:00.000Z` → exactly at cutover → **rejected** (retired key).
- `issued_at 2026-05-01T00:00:00.001Z` → after → **rejected**.
- `issued_at 2026-03-10T08:00:00.000Z` → strictly before → **trusted**, regardless of when verified.

**10:38 dana.whitfield**
That table's correct. Ship it into the runbook verbatim. The `2026-04-30T23:59:59.999Z` vs `2026-05-01T00:00:00.000Z` pair is the one that matters — one millisecond apart, opposite verdicts, and the cutover instant itself is on the rejected side.

**10:39 ola.ferrand**
From the worker's logs those two emit: first "trusted (key k-build-2025b, expired-but-historical)", second "rejected: signing key k-build-2025b retired as of 2026-05-01T00:00:00.000Z". Genuinely valid signature in both, different policy verdict. The rejection dashboard counts only the second kind.

**10:44 ingrid.solberg**
Draft register entry for the sanity check I promised:

> **Event:** Build signing key expiry (scheduled rotation). **Key:** `k-build-2025b`. **Effective:** `2026-05-01T00:00:00.000Z`. **Nature:** Expiry, not compromise; no breach or key exposure. **Prior signatures:** Statements signed by `k-build-2025b` with `issued_at` strictly before `2026-05-01T00:00:00.000Z` remain valid and trusted indefinitely. **From effective instant:** Statements signed by `k-build-2025b` with `issued_at` at or after `2026-05-01T00:00:00.000Z` are rejected as signed by a retired key. **Public key material:** Retained in keyring for verification of historical signatures. **Successor key:** `k-build-2026a`, now the sole production build key.

Accurate?

**10:46 dana.whitfield**
Accurate and complete. That's exactly the policy. The one word I'd stress-test is "indefinitely" and I'm happy with it — there is no second expiry of the historical trust.

**10:47 ruth.callahan**
That register entry is clean and it's what I'll point auditors at. One thing stated plainly for the record, ingrid include it: the reason there is no grace period is a deliberate security decision, not an oversight. We considered a two-week extension requested by release engineering on operational grounds, and declined it because a signing key must have a single unambiguous retirement instant. That instant is `2026-05-01T00:00:00.000Z`.

**10:48 ingrid.solberg**
I'll reference that. "Grace period considered and declined; retirement instant is a hard cutover at `2026-05-01T00:00:00.000Z`." Filing against SEC-2291 as the authoritative compliance record.

**10:49 tomas.berg**
Fine by me. My objection is documented, the decision is documented, and with all-green rollout the objection is mostly moot. I'd rather have argued it and lost than not argued it.

**10:52 priya.raghunathan**
OK, status check. Keyring: `k-build-2026a` fingerprint verified against HSM export (dana, confirm?), `k-build-2025b` public key confirmed staying in `/app/config/keyring.json`. Rollout: all production pipelines green as of 10:31. Compliance: register entry drafted and filing. Anything open?

**10:54 dana.whitfield**
Keyring confirm: `k-build-2026a` fingerprint checked against the HSM export, matches. `k-build-2025b` public key stays — ran the "do not delete" affirmative step, it's ticked. One non-blocking item: on `2026-05-01T00:00:00.000Z` I want someone eyeballing the rejection watch dashboard for the first hour or two in case a pipeline we don't know about fires.

**10:55 priya.raghunathan**
I'll take the cutover watch. `2026-05-01T00:00:00.000Z` is 02:00 my local, which I'm delighted about, but I'd rather watch it than get paged.

**10:56 kenji.watanabe**
Note you did the timezone thing correctly there — "02:00 my local" for the `2026-05-01T00:00:00.000Z` instant, right way round, unlike the analytics on-call this morning. UTC is the source of truth, everything else is a conversion, and the conversion is where people bury the bug.

**10:58 ola.ferrand**
Worker side I've got nothing blocking. The trust logic keys off `key_id` and `issued_at`, compares `issued_at` for `k-build-2025b` against `2026-05-01T00:00:00.000Z`, strictly-before trusts, at-or-after rejects with "signing key retired". `k-build-2026a` trusts as the current production key. Public keys for both stay in the keyring so both verify cryptographically. This is trust policy sitting on top of a valid signature.

**11:00 marcus.lin**
Last one from me. "Sole production build key" means for any NEW release from now on, the only `key_id` ReleaseSentinel should see on a freshly-issued badge is `k-build-2026a`. A brand-new badge showing `k-build-2025b` after the cutover is by definition a mistake.

**11:01 dana.whitfield**
Correct. New releases: `k-build-2026a`, only `k-build-2026a`. A freshly-issued badge — `issued_at` at or after `2026-05-01T00:00:00.000Z` — carrying `key_id: k-build-2025b` is a pipeline that missed the rollover, and it gets rejected. That rejection is the system working as designed, not a false positive.

**11:02 priya.raghunathan**
Alright. I think that's the rotation decided and executed bar the actual cutover instant passing. Summary of who's holding what: dana keyring (done), tomas + owners pipelines (all-green), priya rollout + cutover watch, ingrid compliance filing, ola worker behaviour confirmed. Reconvene only if the rejection dashboard lights up after `2026-05-01T00:00:00.000Z`.

**11:03 tomas.berg**
One more for the long tail: I'll sweep every pipeline config before the 1st, grep-ing for `k-build-2025b` in the signing key field, so if there's another data-exports out there we find it by config inspection, not by rejection.

**11:15 tomas.berg**
Sweep done. `grep -rl 'k-build-2025b' pipelines/` → one hit, `pipelines/legacy-docs/build.yaml`. legacy-docs hasn't built since January and it's not a production release pipeline — it publishes internal docs, no ReleaseSentinel badge involved. Flipped it to `k-build-2026a` anyway for hygiene. Every production pipeline is on `k-build-2026a`.

**11:16 dana.whitfield**
Good sweep. Dashboard says all-green by behaviour, grep says clean by config. Both agree.

**11:17 priya.raghunathan**
Then we're done for today. `k-build-2025b` retires at `2026-05-01T00:00:00.000Z`, hard, no grace period, expiry not compromise, historical badges trusted forever, public key stays in the keyring, `k-build-2026a` is the sole production build key. Rollout all-green. See you on the cutover watch, or not at all if it's quiet, which is the goal.

**11:18 ola.ferrand**
The dream outcome of a rotation is nobody noticing it happened. Aim for boring.

**11:19 ingrid.solberg**
Register entry filed against SEC-2291. Effective `2026-05-01T00:00:00.000Z`. Audit trail complete.

