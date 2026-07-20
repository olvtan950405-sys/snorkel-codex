# #war-room-releasesentinel

## 2026-04-02

**16:41 dana.whitfield**
Paging this channel. SEC-3310 just got escalated to me by the cloud-sec on-call. A contractor laptop backup is sitting in an S3 bucket with no bucket policy and a public ACL, and the tarball contains signing key material. Still confirming which key. Do not tweet.

**16:42 priya.raghunathan**
Which bucket. arn.

**16:43 dana.whitfield**
`arn:aws:s3:::nw-contractor-backups-euw1`. It's in the old contractor account (5591...2043) — the one we were supposed to have decommissioned in Q4. A nightly Macie job flagged it and it only just got in front of a human.

**16:43 priya.raghunathan**
Of course it's the account we thought was dead. Who's the on-call sec director tonight, ruth?

**16:44 dana.whitfield**
Ruth's who I'm about to page. Two minutes, I want the object listing before I wake her.

**16:47 dana.whitfield**
ACL on the object, raw `get-object-acl`:
```
"Grants": [
  {"Grantee": {"Type": "CanonicalUser", "ID": "a19f...c3"}, "Permission": "FULL_CONTROL"},
  {"Grantee": {"Type": "Group", "URI": ".../global/AllUsers"}, "Permission": "READ"}
]
```
AllUsers READ. World-readable. Object is `backups/laptop-jbriggs/2024-11-03/home.tar.zst`, 41 GB.

**16:48 priya.raghunathan**
AllUsers READ on a 41GB tarball with a private key in it. Cool cool cool. Any idea if it's been pulled.

**16:49 dana.whitfield**
Working the CloudTrail question now. That's the whole ballgame — did it sit there unloved or did someone GET it.

**16:52 ruth.callahan**
I'm here. Kids are finally down, maybe an hour before one wakes up, so let's be efficient. Dana, one paragraph, what do we know.

**16:54 dana.whitfield**
Known: a laptop backup for a former contractor (J. Briggs, offboarded Feb 2025) is in a world-readable S3 object in a decommissioned-on-paper account, containing a PEM under `~/.config/northwind/keys/`. I have NOT pulled 41GB — I'm range-GETting just the offset I need. Unknown: which key exactly, and whether anyone external read the object. Everything else is speculation.

**16:55 ruth.callahan**
Good. Speculation stays out of the record. Priya, you're IC on the ops side, I own the security call. Dana keeps digging. Where's the bridge, I'd rather talk some of this.

**16:56 priya.raghunathan**
Bridge is up, same PMI. Warning, it's been flaky all week.

**16:58 ola.ferrand**
On the bridge. Can hear Priya breathing and nobody else. Classic.

**17:00 ruth.callahan**
I keep getting "the host has not yet joined". Forget it, I'll stay in the channel and you relay. This bridge is garbage, someone file a ticket with IT tomorrow.

**17:01 tomas.berg**
Lurking, woke up to eleven pages. What's the scope — a release-signing key or some random dev key. Those are very different Tuesdays.

**17:03 dana.whitfield**
Exactly the question. Range-GET of the PEM header is in:
```
-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEI...
```
Ed25519. The tar entry comment above it is `# nw release signing - legacy`. Fairly confident this is `k-legacy-2024`. Confirming by deriving the public key and diffing against the keyring.

**17:04 tomas.berg**
legacy. that's the 2024 build key. Hasn't been *primary* since we rotated to k-build-2025b, then k-build-2026a in Jan. But it absolutely signed real releases while it was primary — and a couple of services never fully migrated off it.

**17:06 dana.whitfield**
Confirmed:
```
$ ssh-keygen -y -f /tmp/leaked.pem | awk '{print $2}' | base64 -d | sha256sum
6f2c9a...e1  -
```
matches the `k-legacy-2024` entry in `/app/config/keyring.json`. This is our key. It is out.

**17:07 ruth.callahan**
That changes the posture. Confirmed key compromise, not a maybe. SEC-3310 becomes a Sev1. Priya, open the incident record.

**17:08 priya.raghunathan**
Done. INC-2026-0402-01, Sev1, "k-legacy-2024 signing key exposure". Linking SEC-3310. Timeline starts at Dana's 16:41 page.

**17:09 kenji.watanabe**
Joining, saw the sev1 flip. Reading up. Give me a sec before you decide anything irreversible.

**17:12 dana.whitfield**
CloudTrail is the problem. Data events (object-level GetObject) were NOT enabled on this bucket — the account was "decommissioned" so nobody was paying for data-event logging. I can see management events (who changed the ACL) but I cannot see reads.

**17:13 priya.raghunathan**
So we can't prove it was read.

**17:13 dana.whitfield**
Correct. And — this is the important part — we can't prove it wasn't. Absence of read logs is not absence of reads. It's absence of logs.

**17:14 ruth.callahan**
Write that sentence down. That's the sentence that drives tonight's decision. When you can't see, you assume the worst. Keep going.

**17:16 dana.whitfield**
Management events I DO have. The ACL change that made it public:
```
{"eventTime": "2024-11-03T02:14:51Z", "eventName": "PutObjectAcl",
 "userIdentity": {"userName": "contractor-ci"},
 "requestParameters": {"x-amz-acl": "public-read"}, "sourceIPAddress": "51.140.xx.xx"}
```
World-readable since November 2024. Seventeen months.

**17:17 ola.ferrand**
So the window isn't "tonight". It's "since before we even rotated off this key as primary". That's a very large window.

**17:20 priya.raghunathan**
Let's not litigate the threat model on the bridge half of us can't hear. Concrete steps. Dana, what do you need.

**17:22 dana.whitfield**
Three things in parallel. One: lock the bucket — remove the public grant, block-public-access at the account level, quarantine the object as evidence, don't delete it. Two: figure out everything `k-legacy-2024` is trusted to do. Three: decide what ReleaseSentinel does about statements signed with this key.

**17:25 priya.raghunathan**
I took one. `put-public-access-block` applied at account 5591...2043, all four flags true. Object ACL reset to private, tagged `legal-hold=true`. Bucket is no longer world-readable as of now.

**17:26 ruth.callahan**
Good. That stops the bleeding. It does NOT un-leak seventeen months. Everyone clear? Closing the bucket doesn't retroactively make the key secret again.

**17:28 dana.whitfield**
On item two — what trusts `k-legacy-2024`. The keyring at `/app/config/keyring.json` carries public key material ONLY. No `revoked` field, no `allowed_branches`, no expiry. It literally cannot express "this key is dead."

**17:29 kenji.watanabe**
Which is why this channel is the only place the actual policy lives. Terrible property, but the property we have.

**17:30 dana.whitfield**
So the trust is entirely implicit: ReleaseSentinel verifies any statement whose `key_id` is `k-legacy-2024` as long as the Ed25519 signature checks out against the public key. Nothing today says "reject it." Verifies as valid, full stop.

**17:31 ruth.callahan**
So tonight, an attacker holding this key can mint a badge for any artifact and ReleaseSentinel blesses it.

**17:31 dana.whitfield**
Yes. That's the exposure. Not "old releases might be questioned" — new forgeries will be accepted.

**17:32 marcus.lin**
Ok I've been paged four times, I'm here, and I already don't like where this is going. payments-api still signs with k-legacy-2024. Our HSM migration is not done. Please tell me you're not about to kill that key at 5:30 on a Thursday.

**17:33 priya.raghunathan**
It's 5:32. Hi Marcus. Yes, exactly that conversation.

**17:34 ruth.callahan**
You have a seat, Marcus. But I want the security shape first, then your constraint, then we decide. Dana keep going. Tomas, I'll want the release history for this key.

**17:41 marcus.lin**
While Tomas digs — my constraint, plainly. payments-api release cutting still signs badges with k-legacy-2024. The migration to sign in the HSM under a new key is REL-2201 and it's blocked on the HSM PKCS#11 slot config infra hasn't finished. "Two weeks out" for two months. Revoke legacy tonight and our next release literally cannot be signed and cannot ship. And we have a payments hotfix queued for tomorrow.

**17:42 ola.ferrand**
Why is payments the only one still on legacy. orders and search both moved.

**17:43 marcus.lin**
Because payments release signing has to happen inside the HSM for the compliance story, and that path isn't ready, so we've been signing with the software key — which happens to be legacy — as an interim. Supposed to be temporary. It's now load-bearing.

**17:43 kenji.watanabe**
"temporary interim that became load-bearing" is the tagline of this entire company.

**17:46 tomas.berg**
History, reconstructed from the changelog + signing logs:
```
v8.2.1  (release/8.2)   k-legacy-2024   2024-09-12
v8.3.4  (release/8.3)   k-legacy-2024   2024-12-01
# rotation to k-build-2025b
v8.4.0  (release/8.4)   k-build-2025b   2025-06-20
v8.4.1  (hotfix/8.4.1)  k-build-2025b   2025-07-02
# rotation to k-build-2026a (Jan 2026)
v8.5.0  (release/8.5)   k-build-2026a   2026-02-18
```
So the release tags v8.2.1 and v8.3.4 were legacy-signed. Payments ALSO re-signs its own service badges on every deploy, and those are still legacy-signed right up to today. That's Marcus's problem specifically.

**17:48 kenji.watanabe**
Here's where I want to slow everyone down. Two very different questions, don't collapse them:
1. Stop TRUSTING NEW things signed with this key? Obviously yes, immediately, no debate.
2. RETROACTIVELY distrust the historical releases (v8.2.1, v8.3.4, the old payments badges) that were legitimately signed months ago while it was still the real key?
Not the same question. Should not get the same answer on reflex.

**17:49 ruth.callahan**
Make the case for splitting them.

**17:51 kenji.watanabe**
The historical statements were signed when the key was the sanctioned key. The signatures are cryptographically fine and we have signing-log records of when each was issued. Say "everything this key ever touched is poison" and you invalidate months of good releases — v8.2.1 and v8.3.4 still run in places, and every legacy-signed payments badge in prod suddenly fails verification. That's not a security win, that's an outage we inflict on ourselves. The clean answer is a cutoff: distrust anything signed AT OR AFTER the compromise instant, keep trusting what was signed before under the real process.

**17:52 marcus.lin**
Thank you. Yes. A time cutoff. Draw a line, everything before it is fine, everything after is suspect. The engineer in me likes it — clean, defensible, maps to how we think about rotation normally.

**17:54 dana.whitfield**
I want to like it too. But back to my 17:13 sentence. The cutoff assumes we KNOW when the key was compromised. We don't. The ACL went public in November 2024. If an attacker pulled the key then, "signed before the compromise instant" is meaningless — the compromise instant is seventeen months ago, before most of the history we're talking about.

**17:55 kenji.watanabe**
But no evidence of a forged historical badge. If the key was stolen in Nov 2024 and used to forge v8.3.4 there'd be two conflicting badges for the same digest and we'd see it.

**17:56 dana.whitfield**
Would we? Have we actually looked for duplicate badges across the whole 17 months? I haven't run that job and I don't think anyone has.

**17:57 kenji.watanabe**
...no. Fair. Not yet.

**17:58 priya.raghunathan**
Ok this is the crux and the bridge dropped Ola again, keep it in text. Ruth, this is a you-decision. Cutoff (trust the pre-compromise history) or scorched earth (distrust everything the key ever signed).

**18:04 ruth.callahan**
Let me reason on the record. Kenji's cutoff is the RIGHT answer if we have good forensics — the answer I'd give in a week with a clean timeline. Problem: I don't have a week and I don't have a timeline. I have a key world-readable for seventeen months, zero object-level read logs, no completed sweep for forged badges, and a payments release path still actively signing with the thing. Every unknown points the same direction — I can't establish a trustworthy "before." And a cutoff is only as good as the instant you draw it. Draw it at "compromise", be wrong about when compromise happened, and I've certified forgeries as genuine.

**18:05 kenji.watanabe**
So draw it at November 2024. The ACL date. That's conservative.

**18:06 ruth.callahan**
And certify we KNOW nothing before Nov 2024 was touched? I don't know that either. The backup is from Nov 2024 but the key existed and was in use before that. I have no idea when it first left our control. Any cutoff instant I pick is a claim of knowledge I don't have.

**18:08 dana.whitfield**
Where I land too, and I hate it, because Kenji isn't wrong about the collateral damage. But I can defend "we assumed the worst and it cost us some re-verification." I cannot defend "we drew a comforting line, and a forged artifact was on the trusted side of it."

**18:10 ruth.callahan**
Right. Here's the call for tonight. We treat `k-legacy-2024` as fully compromised. Not "compromised going forward" — compromised, period. Every statement it has EVER signed is treated as untrusted, regardless of when it was issued. No time cutoff. Burn it all. Assume everything it ever signed is poisoned until forensics proves otherwise.

**18:11 marcus.lin**
Ruth. That takes out every payments badge in prod. Every one. Not re-verification — payments failing trust checks across the board.

**18:11 kenji.watanabe**
And v8.2.1 and v8.3.4. Legitimate releases, retroactively distrusted, on a hunch that maybe the key was stolen in 2024.

**18:12 ruth.callahan**
I hear both of you. I'm overruling both of you for tonight. Let me be precise. Priya, in the record verbatim.

**18:14 ruth.callahan**
Decision, INC-2026-0402-01: `k-legacy-2024` is REVOKED as of `2026-04-02T17:30:00.000Z` — that instant being when Dana confirmed the derived public key matched the keyring entry and we knew for certain the key was exposed. Effective at that revocation instant, ReleaseSentinel treats any statement whose `key_id` is `k-legacy-2024` as UNTRUSTED, without regard to the statement's `issued_at`. There is no time cutoff. A statement signed by this key in September 2024 is exactly as untrusted tonight as one signed at 17:29 today. Total blast radius. Every statement the key has ever signed is poisoned until proven otherwise.

**18:15 priya.raghunathan**
Recorded verbatim. Revocation instant `2026-04-02T17:30:00.000Z`. key_id `k-legacy-2024`. No issued_at cutoff — all statements untrusted regardless of issue time.

**18:15 ingrid.solberg**
Compliance is on, sorry, paged late. I need the exact revocation instant nailed down for the audit record, unambiguous. Someone say it once more, precisely, timezone and all.

**18:16 dana.whitfield**
`2026-04-02T17:30:00.000Z`. UTC. That is the revocation instant for `k-legacy-2024`. The moment the bucket exposure was confirmed against the keyring. From that instant, no statement bearing key_id k-legacy-2024 is trusted, irrespective of when it was issued.

**18:16 ingrid.solberg**
Thank you. `2026-04-02T17:30:00.000Z`, revocation of k-legacy-2024, total scope, no issued_at boundary. That's what goes in the compliance ledger.

**18:18 kenji.watanabe**
For the record I object to the retroactive part. Not the revocation — obviously revoke it. The part where we distrust historical releases that were legitimately signed months ago. We're going to regret invalidating good history on incomplete forensics.

**18:19 ruth.callahan**
Your objection is recorded, and it's reasonable. Here's what I'll give you: forensics revisit the historical question tomorrow, with the duplicate-badge sweep actually run and a real timeline. If it comes back clean, we have a conversation about whether the pre-compromise history can be re-trusted. But that's a tomorrow conversation with data. TONIGHT, with no data, we assume the worst. I'm not certifying seventeen months of history as safe at six in the evening on vibes.

**18:20 kenji.watanabe**
Understood. Tomorrow, with the sweep run. I'll hold you to "revisit."

**18:21 marcus.lin**
So what happens to payments right now. Concretely. "Every payments badge is untrusted" means what, at 6:20pm.

**18:23 ola.ferrand**
Mechanically: ReleaseSentinel fails verification for any badge whose statement.key_id is k-legacy-2024. Old or freshly minted, doesn't matter. Legacy-signed payments deploy badges stop being trusted the next time the worker evaluates them.

**18:24 marcus.lin**
A de facto freeze. We can't cut a new one — legacy is the only signing path we have wired up — and the existing ones lose trust status. payments frozen coming and going.

**18:25 ruth.callahan**
For tonight, yes. Payments release path is frozen until you're signing with a non-compromised key. I'm sorry, genuinely, but there's no version of "the signing key is public on the internet" where the answer is "keep signing with it."

**18:27 marcus.lin**
Then I want an exception. Narrow, time-boxed: payments keeps signing with k-legacy-2024 for the queued hotfix tomorrow, under monitoring, while we sprint REL-2201 to close the HSM migration. You're the only one who can grant it, Ruth. I'm asking.

**18:28 ruth.callahan**
No. Not like this and not tonight.

**18:29 marcus.lin**
Ruth, the hotfix is a customer-facing payments bug, it's queued, people expect it.

**18:30 ruth.callahan**
Understood, still no. You're asking me to grant a signing exception for a key confirmed public ninety minutes ago, mid-Sev1, on a flaky bridge, with forensics maybe ten percent done. That's precisely the wrong condition to grant one. Exceptions granted in a panic at night are how you get a second incident.

**18:31 ruth.callahan**
The path: file it properly. There's a process for exactly this — a REL exception request, written justification, scope, expiry date, compensating controls, in writing where I can weigh it with a clear head and the forensics in front of me. I'll look first thing tomorrow. I am not granting a policy exception verbally on a war-room bridge at night.

**18:32 marcus.lin**
...fine. I'll file it. For the record I think the payments freeze hurts more than the theoretical attacker.

**18:33 ruth.callahan**
Noted, file it anyway, and we weigh exactly that trade-off tomorrow in writing. Tonight the key is revoked, no exception granted, payments frozen. That's the state.

**18:34 ingrid.solberg**
For the audit trail: as of this thread, ZERO exceptions granted for k-legacy-2024. Marcus intends to file a request. That request does not yet exist and is not approved. Correct?

**18:34 ruth.callahan**
Correct. No exception exists, no exception is approved. The request will be filed and considered tomorrow.

**18:35 marcus.lin**
Correct. Nothing granted. Filing REL-2209 tonight so it's in the queue for morning.

**18:40 priya.raghunathan**
Ola, does the worker need a change to enforce this or does it already?

**18:42 ola.ferrand**
It does NOT already. The keyring has no revocation field — no line in `/app/config/keyring.json` you can flip to `"revoked": true`. The worker trusts any key present whose signature verifies. So "revoked as of 17:30Z" currently lives only in this chat and in Ingrid's ledger — the software doesn't know about it.

**18:43 kenji.watanabe**
So how does it get enforced tonight. A decision the worker can't see is a Post-it note, not a control.

**18:44 dana.whitfield**
Options, none clean. (a) Remove the k-legacy-2024 public key from the keyring entirely — then signatures don't verify because there's no key to verify against. Blunt, but produces "untrusted." (b) An out-of-band denylist the worker reads — doesn't exist as code today.

**18:45 ola.ferrand**
Pull the public key and every legacy-signed badge fails because the verifier can't find a key for that key_id. Which is exactly the behavior Ruth ordered — total distrust, no time cutoff, because the key isn't there to verify anything anymore.

**18:46 kenji.watanabe**
Right behavior for the wrong reason. "Untrusted because revoked" and "untrusted because the key vanished" are different states the worker can't tell apart. But tonight I'll take it.

**18:47 dana.whitfield**
Hold on — we can't yank it without checking one thing. `k-ci-sandbox` and the legacy key are different entries, right? I do not want to fat-finger the keyring and take out the sandbox pipeline's key.

**18:48 ola.ferrand**
Different entries. `k-ci-sandbox` stays — the sandbox pipeline needs it in the keyring and it's not implicated. We touch ONLY the `k-legacy-2024` entry.

**18:52 dana.whitfield**
PR up: #4471, "remove k-legacy-2024 public key from keyring per INC-2026-0402-01". `git show --stat` = one file, `config/keyring.json`, +0 -6. Removes only the legacy entry; others untouched. Ola review, Tomas second.

**18:54 tomas.berg**
Reviewed. Removes exactly the one entry. Approving the *mechanism*; the *policy* is Ruth's call above.

**18:55 ruth.callahan**
Approve and merge. That's the enforcement of the 17:30Z revocation for tonight. It's blunt and I want a proper revocation mechanism designed, but not tonight.

**19:05 dana.whitfield**
Merged #4471, config rolled to all ReleaseSentinel workers. `k-legacy-2024` public key is gone from the keyring in prod. Any badge with key_id k-legacy-2024 now fails verification for lack of a key. Enforces "untrusted, all of it, no cutoff."

**19:07 marcus.lin**
It's enforced alright. My phone lit up. payments-api release health check just went red — running deploy badges are legacy-signed and failing trust. Told you.

**19:09 priya.raghunathan**
Is anything actually DOWN or is it trust-status red? Different things.

**19:09 marcus.lin**
Trust-status red. Service serves traffic fine. But our release gate shows payments as "unverified artifact" and it'll block the next promote. That's the freeze. Nothing crashing, we just can't ship.

**19:10 priya.raghunathan**
Serving fine, can't promote. Intended state per Ruth's call. Logging as expected.

**19:20 dana.whitfield**
Sanity check on enforcement — a legacy badge and a non-legacy badge through a worker:
```
$ releasesentinel verify --badge /tmp/legacy-test.png
key_id: k-legacy-2024   result: UNTRUSTED (no key for key_id in keyring)
$ releasesentinel verify --badge /tmp/v8.5.0-payments.png
key_id: k-build-2026a   result: TRUSTED
```
Good. k-build-2026a still trusts. We only killed legacy.

**19:35 dana.whitfield**
Everything above is containment. Now the forensics question: was this key EVER used to forge something in those 17 months. If yes, the total-distrust call is fully vindicated; if no, it's still defensible but Kenji gets his re-trust conversation tomorrow. Running the duplicate-badge sweep — for every artifact_digest, count distinct valid badges; any digest with two different legacy-signed badges is a smoking gun. ~2.1M badges, going to take a while.

**20:15 dana.whitfield**
Ok, chased something for the last hour that I now think is a red herring — flagging so nobody else burns time on it. The sweep threw a cluster of ~400 legacy-signed badges all with issued_at in a two-hour window on `2025-03-14T02:*`, which looked like a bulk-forgery event. Adrenaline spiked. But:
```
$ grep 2025-03-14 signing-audit.log | head -1
2025-03-14T02:11Z  k-legacy-2024  payments-api  REL-1804 backfill re-sign (approved)
```
It was OUR backfill. REL-1804, March 2025, when payments re-signed a batch after the digest-format change. All in the signing audit log, all approved, all from our own CI runner IPs. Not an attack. Sorry for the pulse-raise.

**20:18 kenji.watanabe**
oh god yeah, the REL-1804 backfill, I remember that. And see, this is my whole point — the "scary" thing turned out to be legitimate historical activity. That's what retroactively distrusting history does: it turns our own normal operations into suspects.

**20:19 ruth.callahan**
It also means the sweep is doing its job. A red herring correctly identified is a good outcome. Doesn't change the decision — informs tomorrow's re-trust conversation.

**20:52 dana.whitfield**
Sweep at 71%. Still nothing. But "clean sweep" does not equal "key was never copied" — it equals "if it was copied, it wasn't used in a way this sweep detects." Not grounds to reverse anything.

**21:10 dana.whitfield**
Sweep 100%. No evidence of misuse of k-legacy-2024 across 2.1M badges. No forged duplicates, no impossible issue times, no foreign source IPs in the signing path. Artifact: `https://northwind.internal/inc/2026-0402-01/legacy-sweep.json`. Caveat for the record: absence of detected misuse is not proof of no compromise, especially with no object-read logs on the bucket. Nobody reads this and decides we overreacted — we revoked a confirmed-public key.

**21:11 kenji.watanabe**
So the tomorrow question, cleanly: given a clean sweep, do we re-trust the pre-compromise historical statements, or keep total distrust. I'm on record for re-trusting the history. A tomorrow decision with Ruth, in daylight.

**21:12 ruth.callahan**
Yes. Tomorrow, in writing, with this sweep as evidence. Tonight the posture is unchanged: `k-legacy-2024` revoked as of `2026-04-02T17:30:00.000Z`, every statement it ever signed treated as untrusted, no exceptions. The clean sweep does not alter tonight's posture by one bit.

**21:20 marcus.lin**
And payments stays frozen through all this. I've filed REL-2209, scope "payments-api release signing continues on k-legacy-2024 under monitoring until REL-2201 HSM migration completes", with proposed expiry and monitoring. In your queue, Ruth. Not asking for a decision tonight — just, it exists in writing like you asked.

**21:21 ruth.callahan**
Good, that's the right way to ask. I'll review REL-2209 tomorrow with the forensics. No commitment either way. A request in a queue, not an approval.

**21:22 ingrid.solberg**
For the ledger: REL-2209 exists as a REQUEST, status "open/unreviewed". Not granted. k-legacy-2024 remains revoked with zero active exceptions.

**21:35 priya.raghunathan**
Open items for tomorrow so people can go to bed: forensics review of the clean sweep + the re-trust question, the REL-2209 payments exception request, and designing a real revocation mechanism because "delete the key from the keyring" is not it.

**21:36 ola.ferrand**
On that last one — the ONLY way we could enforce a revocation was to physically delete the public key, which is embarrassing. The keyring should be able to say "present but not trusted for signing after instant T." It can't. Loudest design gap now.

**21:37 dana.whitfield**
Agreed, I'll write it up. But even a proper mechanism has to answer what we fought about tonight: revocation from an instant forward, or everything the key ever signed. Tonight's answer was "everything, no cutoff." A future mechanism needs to express that AND a cutoff — opposite postures, the design has to hold both.

**21:50 yusuf.adeyemi**
one dumb question before I drop. the sandbox key, k-ci-sandbox — still in the keyring and still trusted, right? we didn't accidentally sweep it up in the panic?

**21:51 ola.ferrand**
Still in the keyring, still trusted, untouched. We only removed k-legacy-2024. k-ci-sandbox, k-build-2025b, k-build-2026a all present and trusted. Sandbox pipeline fine.

**21:52 yusuf.adeyemi**
great. night all. hope the kid on the bridge goes back to sleep.

**21:52 ruth.callahan**
That's mine, sorry — he's been narrating the whole incident from the doorway. Go to bed Yusuf.

**22:05 dana.whitfield**
Last housekeeping. Opened SEC-3311 for the decommission-that-wasn't (account 5591...2043 meant to be dead, had a live public bucket) and SEC-3312 to rotate any OTHER credentials in that laptop backup — if the signing key was in there, what else was. Both linked to INC-2026-0402-01.

**22:20 tomas.berg**
One more and I'm out. The payments deploy badges now failing trust — nobody "fixes" that by re-signing them with a different key tonight. That's minting new attestations mid-incident and it'd muddy the forensics. Leave them red until the exception or the migration resolves it.

**22:21 marcus.lin**
I wasn't going to. Agreed, on record.

**22:40 kenji.watanabe**
Recording my objection one final time so it's not buried mid-thread: I disagree with retroactively distrusting the legitimately-signed historical releases (v8.2.1, v8.3.4, pre-today payments badges) on the strength of a compromise we can't time and a sweep that came back clean. I accept the revocation and the freeze. I expect the re-trust question reopened tomorrow with the sweep as evidence. Overruled for tonight, not conceded.

**22:41 ruth.callahan**
Recorded, in full — a fair objection from a careful engineer. For tonight it's overruled: with no timeline and no way to bound the compromise, we assume everything the key ever signed is poisoned. Tomorrow, with `legacy-sweep.json` in front of us, we revisit whether that total scope can be narrowed. That's a promise, Kenji, and it's in the record.

**22:42 kenji.watanabe**
Good enough. Night.

**23:05 ola.ferrand**
Workers healthy on the fleet dashboard, verification rate normal minus the expected legacy failures. Night.

**23:30 ruth.callahan**
Final word, then this channel goes quiet till morning. The decision tonight was made under pressure with incomplete forensics, and I want that stated plainly: we did not have enough to draw a defensible time cutoff, so we chose the conservative, painful option — treat every statement k-legacy-2024 ever signed as untrusted, from the revocation instant `2026-04-02T17:30:00.000Z`, with no regard to when anything was issued. That may prove to be more than we needed. We find out tomorrow. Tonight, we assume the worst. Good night.

**23:48 ingrid.solberg**
Ledger sealed. Recorded exactly: revocation of k-legacy-2024 effective `2026-04-02T17:30:00.000Z`; scope = all statements ever signed by the key, no issued_at boundary; exceptions granted = none; REL-2209 = open/unreviewed; forensics = revisit 09:00. Timestamps and wording locked. Night all.
