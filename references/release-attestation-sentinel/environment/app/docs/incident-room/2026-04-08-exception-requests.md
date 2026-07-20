# #war-room-releasesentinel

## 2026-04-08

**08:47 marcus.lin**
Morning. Reopening the war room thread because I need to get ahead of something before standup. payments-api still has a hard dependency on `k-legacy-2024` for release signing and there is no way we clear that before the HSM cutover lands. I want to file a formal exception request today, not hallway-discuss it.

**08:49 marcus.lin**
Context for anyone joining: after the cutoff we cannot use that key for anything, I get it. But our migration to the HSM-backed build key is genuinely mid-flight and the pipeline that mints payments-api badges still calls the legacy key. If we flip the signing config today the release train stops. So I need a written, time-boxed exception.

**08:51 priya.raghunathan**
This is the right channel for it but it is not mine to grant. Exceptions to the signing policy go through ruth. What I can do is make sure the request is actually complete so she is not chasing you for fields. Do you have a Jira open?

**08:52 marcus.lin**
Opening one now. Give me two minutes.

**08:55 marcus.lin**
SEC-3341 — "Exception: payments-api continue signing with k-legacy-2024 through HSM migration". I'll paste the form once I fill it.

**08:56 dana.whitfield**
Flagging before this goes any further: I own the keyring and I want it on record that the keyring itself carries no exception state. `/app/config/keyring.json` is public key material only. Whatever ruth grants lives in the incident record and nowhere else — there is no field in the keyring that says "this key is allowed for payments-api until date X". So the wording of the exception has to be exact, because the wording IS the control. There is nothing else backing it.

**08:57 priya.raghunathan**
Which is exactly why ingrid should be in this thread from the start and not brought in at the end to bless something already half-agreed. Pulling her in.

**08:58 ingrid.solberg**
Here. I have opinions about expiry wording, you will all be shocked to learn. Marcus, when you paste the form, do not write "expires end of June" or "expires June 30" in prose and consider it done. We will pin an instant. I mean it.

**09:01 marcus.lin**
Understood. Here's the form as filed on SEC-3341:

```
EXCEPTION REQUEST — Northwind Platform Release Security
------------------------------------------------------
ID (assigned by security):   EX-14
Jira:                        SEC-3341
Requesting team:             payments-api
Requestor:                   marcus.lin
Policy being excepted:       Prohibition on release-signing with a revoked key
Key in question:            k-legacy-2024
Scope requested:             payments-api release badges only
Reason:                      HSM migration in flight; production build key
                             (HSM-backed) not yet wired into the payments-api
                             signing pipeline. Cutting over today halts the
                             release train.
Duration requested:          Until HSM migration complete; hard backstop end of Q2
Compensating controls:       (to be filled with security)
Approver:                    ruth.callahan (pending)
Review date:                 (to be set)
```

**09:02 marcus.lin**
"Hard backstop end of Q2" is deliberately vague because I know ingrid is going to make me pin it. Consider that a peace offering.

**09:03 ingrid.solberg**
Noted and appreciated but "end of Q2" is still prose and I will still make you pin it. Q2 ends June 30. What does "end of June 30" mean to a signing pipeline that stamps `issued_at` down to the millisecond? That is the whole argument and we are going to have it now rather than at 23:59 on some Tuesday in June.

**09:05 ruth.callahan**
Reading in. I'm the only one who can sign this off so let me set the frame. I am inclined to grant EX-14 for payments-api specifically, because your migration is genuinely blocked on infra we do not control — the HSM provisioning ticket has been stuck in their queue for three weeks. That is a real, documented blocker, not a "we didn't get to it." That distinction is going to matter a lot in about an hour, remember I said that.

**09:06 marcus.lin**
Thank you. What do you need from me to make it final.

**09:07 ruth.callahan**
Compensating controls, a firm expiry instant, a named review date, and I want dana to co-sign the control list since he owns the key material. Let's do the controls first, then ingrid can run her expiry inquisition.

**09:08 ola.ferrand**
Lurking. One thing worth saying while you do controls: ReleaseSentinel does not read any of this. The worker checks the signature against the public key in the keyring and that's the mechanical extent of it. So an exception is a human/process control — it means "we, the org, accept a payments-api badge signed with the legacy key until date X." Nothing in the code enforces the boundary. If a search-api badge shows up signed with that key, the worker will happily verify the signature too, because the key is still in the keyring. Whoever reviews the badge stream has to know that only payments-api is covered.

**09:09 dana.whitfield**
That's the crux, thank you ola. The exception is narrow by policy, not by mechanism. Which means the controls have to include somebody actually watching for out-of-scope use.

**09:10 ruth.callahan**
Right. Dana, draft the control list.

**09:14 dana.whitfield**
Compensating controls for EX-14, first pass:

```
COMPENSATING CONTROLS — EX-14 (payments-api / k-legacy-2024)
1. Scope is payments-api release badges ONLY. Any badge signed with
   k-legacy-2024 whose statement.service != "payments-api" is an
   incident, not a covered release.
2. Every payments-api release signed under this exception is logged to
   the release-attestation register with the badge digest and the
   issued_at instant, so we can prove after the fact that each one fell
   inside the exception window.
3. Weekly review of k-legacy-2024 usage in the badge stream. dana +
   marcus. Anything not payments-api gets escalated same day.
4. HSM migration status reported weekly on SEC-3341. If the infra
   blocker clears early, the exception is retired early — it is a
   ceiling, not a quota.
5. On expiry, payments-api signing config MUST fail closed. No badge
   signed with k-legacy-2024 after the boundary instant is covered by
   anything. It is just an unauthorized signature at that point.
```

**09:15 marcus.lin**
All acceptable. Point 5 is the one I'll be judged on and I know it.

**09:16 kenji.watanabe**
Late, orders-api here, reading up. One question on control 1 — "statement.service != payments-api". The service string is inside the signed statement, right? So it's covered by the signature, someone can't just relabel a search-api badge as payments-api without re-signing. Good. Just wanted that on the record because otherwise control 1 is theatre.

**09:17 dana.whitfield**
Correct. `service` is a field inside the signed statement, so it is bound by the Ed25519 signature. You cannot flip it without the private key. Control 1 has teeth.

**09:18 ruth.callahan**
Good. Control list accepted, dana and I both co-sign it. Ingrid, the floor is yours. Expiry.

**09:20 ingrid.solberg**
Thank you. Here is the problem stated plainly. Marcus wrote "hard backstop end of Q2". Someone reading that in three months will say "the exception runs through June 30, so a release signed on June 30 is fine." Someone else will say "no, it expired at the start of June 30." Those are different by a full day and in audit terms a full day of unauthorized signing is a finding. We do not leave that to interpretation.

**09:21 marcus.lin**
My instinct is June 30 is included. "Through end of Q2" — the 30th is the last day of Q2, so the 30th is in.

**09:22 ingrid.solberg**
That is exactly the instinct I am here to kill. "The 30th is in" is a calendar-day statement. Signatures are not calendar days. A badge carries `issued_at` as a millisecond-precision UTC instant. There is no "day" for the worker or the register to reason about — there is an instant, and it is either before the boundary or it is not. So we do not get to say "the 30th". We say "the boundary is instant T; a statement with issued_at before T is covered; a statement with issued_at at or after T is not." One comparison, no ambiguity.

**09:23 tomas.berg**
Release eng, arriving. I'll say the thing tooling people always have to say: pick a boundary that is trivial to reason about at 2am. Midnight UTC is that boundary. Anything else and someone is doing timezone math during an incident.

**09:24 ingrid.solberg**
Agreed, and that is the proposal. The exception lapses at `2026-06-30T00:00:00.000Z`. That instant is the boundary. A statement whose `issued_at` is at or after `2026-06-30T00:00:00.000Z` is NOT covered by EX-14. Which means the last instant actually covered is the final millisecond of 2026-06-29 — `2026-06-29T23:59:59.999Z`. June 30 as a calendar day is entirely outside the exception.

**09:25 marcus.lin**
Wait. So "expires June 30" actually means "June 30 is already too late". That is the opposite of what I would have assumed reading the form.

**09:26 ingrid.solberg**
Yes. And that gap between what you assumed and what the instant says is precisely why we write the instant and not the prose. "Expires June 30" is a trap sentence. `2026-06-30T00:00:00.000Z` is not. If you want the 30th to be a covered signing day you have to ask for a different boundary — `2026-07-01T00:00:00.000Z` — and justify the extra day. Do you want to ask for that?

**09:28 marcus.lin**
No. HSM provisioning is projected to complete around June 12, so I have margin either way. I'm not going to fight for a day I don't need and hand you an audit finding. `2026-06-30T00:00:00.000Z` is fine.

**09:29 dana.whitfield**
For the record I strongly prefer we take the tighter boundary when the requestor doesn't need the extra day. Every covered instant of a revoked key is risk we are choosing to hold. If marcus is done by mid-June, the exception is a safety margin, not a plan.

**09:30 priya.raghunathan**
Can we make sure the exact same string is what lands in the register and on the Jira? I have watched two "midnights" disagree because one had a trailing offset and one was Z. I want `2026-06-30T00:00:00.000Z`, that exact literal, everywhere. Milliseconds and the Z.

**09:31 ingrid.solberg**
Yes. The canonical string is `2026-06-30T00:00:00.000Z`. Not `2026-06-30T00:00Z`, not `2026-06-30`, not "June 30". The full millisecond form with the Z. Anyone who transcribes it differently has introduced a defect.

**09:32 kenji.watanabe**
Sanity check the comparison direction one more time because this is the part people get backwards. Covered means `issued_at < 2026-06-30T00:00:00.000Z`. Not covered means `issued_at >= 2026-06-30T00:00:00.000Z`. Strictly-less-than on the near side, greater-or-equal on the far side. The boundary instant itself is on the not-covered side.

**09:33 ingrid.solberg**
Exactly right. The boundary belongs to the excluded side. `2026-06-30T00:00:00.000Z` itself is not covered — a badge stamped at precisely that instant is already outside EX-14. Covered is strictly before it.

**09:34 ola.ferrand**
Small pedantry since we're being precise: `issued_at` is what the signer stamps into the statement, and it's inside the signed blob, so it can't be tampered with post-hoc. But it's also self-attested — whoever signs decides what instant to write. That's fine for this control because the point is auditability, not adversarial timestamp defense. Just noting that "issued_at" is the signer's claim about when, and that's the field we compare. Nobody get clever later and start comparing against wall-clock receipt time; the instant that matters is the one in the statement.

**09:35 ingrid.solberg**
Correct and important. We compare `statement.issued_at` against `2026-06-30T00:00:00.000Z`. Not the time the badge was ingested, not the time ReleaseSentinel ran. The signed instant.

**09:37 ruth.callahan**
Good. Then EX-14 is decided. Let me state it cleanly so there is one authoritative message to point at.

**09:38 ruth.callahan**
EX-14 is GRANTED. Scope: payments-api release badges only. Effect: payments-api may continue signing release badges with `k-legacy-2024` after the revocation, notwithstanding the general prohibition, for the duration of this exception. Boundary: the exception lapses at `2026-06-30T00:00:00.000Z`. A statement whose `issued_at` is at or after `2026-06-30T00:00:00.000Z` is NOT covered — the last covered instant is `2026-06-29T23:59:59.999Z`. Approver: me, ruth.callahan. Co-signed control list: dana.whitfield. Jira: SEC-3341. Review date: 2026-05-15, and weekly on SEC-3341 until then. This applies to payments-api and to no other service.

**09:39 marcus.lin**
Received and thank you. Updating SEC-3341 with the final form now.

**09:40 marcus.lin**
Final form on SEC-3341:

```
EXCEPTION REQUEST — GRANTED
------------------------------------------------------
ID:                          EX-14
Jira:                        SEC-3341
Requesting team:             payments-api
Requestor:                   marcus.lin
Key:                        k-legacy-2024
Scope:                       payments-api release badges ONLY
Effect:                      May continue signing payments-api release
                             badges with k-legacy-2024 after revocation
Lapses at:                   2026-06-30T00:00:00.000Z
Covered:                     statement.issued_at < 2026-06-30T00:00:00.000Z
Not covered:                 statement.issued_at >= 2026-06-30T00:00:00.000Z
Last covered instant:        2026-06-29T23:59:59.999Z
Approver:                    ruth.callahan
Control list co-sign:        dana.whitfield
Compensating controls:       see thread 2026-04-08 / SEC-3341 comment 4
Review date:                 2026-05-15 (weekly status on SEC-3341)
```

**09:41 ingrid.solberg**
That's clean. The literal is right in every field. I'm satisfied. This is the record.

**09:42 priya.raghunathan**
One down. Can we breathe for five minutes before the next one.

**09:44 yusuf.adeyemi**
Ah, timing. search-api here. I have basically the identical situation and marcus just wrote the template for me. Can I file the same exception for search-api? Our signing pipeline also still points at `k-legacy-2024`.

**09:45 priya.raghunathan**
No five minutes then. Fine. Open a separate Jira, don't append to SEC-3341, this needs its own paper trail.

**09:46 yusuf.adeyemi**
On it. SEC-3342.

**09:48 yusuf.adeyemi**
Filed. Copied marcus's form basically verbatim:

```
EXCEPTION REQUEST — Northwind Platform Release Security
------------------------------------------------------
ID (assigned by security):   EX-15
Jira:                        SEC-3342
Requesting team:             search-api
Requestor:                   yusuf.adeyemi
Key:                        k-legacy-2024
Scope requested:             search-api release badges only
Reason:                      HSM migration in flight; can't cut over yet.
Duration requested:          Same backstop as EX-14
Compensating controls:       same shape as EX-14
Approver:                    ruth.callahan (pending)
Review date:                 (to be set)
```

**09:49 ruth.callahan**
Leaning yes on this, honestly. It's the same key, the same migration program, the same backstop. If I granted payments-api I'd need a reason not to grant search-api, and on the face of it I don't have one. Let me look at your migration ticket and I'll likely rubber-stamp it with the same boundary and controls.

**09:50 marcus.lin**
Congrats yusuf, welcome to the exception club. Misery loves company. Same `2026-06-30T00:00:00.000Z` boundary presumably.

**09:51 yusuf.adeyemi**
Appreciated. Yeah I'll take the identical terms, less for anyone to remember that way.

**09:52 tomas.berg**
While ruth looks — if both payments-api and search-api are under the same exception with the same boundary, that's actually cleaner for the release train, I only have to track one date. I'll pencil June into the release calendar as "legacy key sunset" for both.

**09:53 priya.raghunathan**
Don't pencil anything in ink yet. Ruth said leaning, not granted. But yeah if it lands it lands on the same instant.

**09:54 kenji.watanabe**
Adding search-api to my mental model of "services allowed to sign with the legacy key" — payments-api and search-api. Will update the review checklist accordingly once it's official.

**09:55 ruth.callahan**
Hold on. Yusuf, where is your HSM provisioning ticket? I'm looking at the infra queue and I see payments-api's request stuck three weeks. I don't see one for search-api at all.

**09:57 yusuf.adeyemi**
Uh. Let me check.

**10:01 yusuf.adeyemi**
Okay. So. We don't have one open. The honest answer is we scoped the HSM migration, put it in the backlog, and haven't started. It's not blocked. We just haven't picked it up.

**10:02 ruth.callahan**
That changes everything, and it's exactly the distinction I flagged at 09:05. EX-14 exists because payments-api is *blocked* on infra they don't control — provisioning stuck in someone else's queue for three weeks, documented. That's a real external blocker and the exception buys them time they cannot otherwise create. search-api is not blocked. search-api hasn't started. Those are not the same request wearing different names.

**10:03 yusuf.adeyemi**
That's fair. I'll be honest, I filed it because marcus filed it, not because I'd hit a wall.

**10:04 ruth.callahan**
Then EX-15 is DENIED. Let me be completely unambiguous because two minutes ago I said "leaning yes" and people started planning around it. I was wrong to say that before checking the blocker. search-api does not get an exception. The remedy for "we haven't started our HSM migration" is to start it, not to keep signing with a revoked key. An exception is for when you cannot comply despite trying; it is not a way to defer trying.

**10:05 dana.whitfield**
Strong agree and I want it recorded that this is the correct call. The moment we grant an exception to a team that simply hasn't done the work, the exception process becomes a bypass and every team files one. The blocker requirement is the entire integrity of the mechanism. payments-api met it. search-api didn't. And to be blunt about the asymmetry: the keyring cannot tell these two cases apart. `k-legacy-2024` is one key. If we'd granted EX-15 there would be two services' worth of legacy-signed badges in the stream and the only thing distinguishing "covered" from "incident" would be a service string plus a memory of two different Jira decisions. One covered service is a control a human can actually hold in their head during a review. Two, one of which was a favour, is how you end up waving through the third.

**10:05 priya.raghunathan**
That's the operational argument and it's the one that lands for me. Reviewer cognitive load is a real control. Keep the covered set as small as the blockers justify.

**10:06 ingrid.solberg**
And from a compliance angle the denial is cleaner to defend than the grant would have been. "We granted an exception to a team that had not begun remediation" is a finding waiting to happen. "We denied it and told them to start" is a healthy control operating as designed. EX-15 denied, reason recorded, done.

**10:07 marcus.lin**
Sorry yusuf. I jinxed you with the welcome-to-the-club thing.

**10:08 yusuf.adeyemi**
Nah, it's the right call, I can't argue it. So to be clear about what I actually have to do: search-api needs to be off `k-legacy-2024` by the general deadline like everyone else, no extension, and I need to open the HSM ticket today.

**10:09 ruth.callahan**
Correct. Open the provisioning ticket today, get in the queue, and if — IF — you later hit a genuine external blocker the way payments-api did, come back and file a fresh request with the blocker documented. That would be a new exception on its own merits, not a revival of EX-15. EX-15 is closed denied.

**10:10 yusuf.adeyemi**
Understood. Opening the infra ticket now. Closing SEC-3342 as denied with your reason pasted in.

**10:11 yusuf.adeyemi**
Updated SEC-3342:

```
EXCEPTION REQUEST — DENIED
------------------------------------------------------
ID:                          EX-15
Jira:                        SEC-3342
Requesting team:             search-api
Requestor:                   yusuf.adeyemi
Decision:                    DENIED by ruth.callahan
Reason:                      No genuine external blocker. HSM migration
                             not started (not blocked). Exception process
                             is for teams that cannot comply despite
                             remediation in progress; deferral of work is
                             not a qualifying reason.
Remedy:                      Open HSM provisioning ticket; comply by the
                             general deadline. May refile with a
                             documented blocker if one genuinely arises.
```

**10:12 kenji.watanabe**
Reverting my mental model. Striking search-api from the "allowed to sign with legacy key" list. Back to payments-api only.

**10:13 tomas.berg**
And I'm erasing the search-api pencil mark from the release calendar. Legacy-key sunset note stays for payments-api only, dated to the EX-14 boundary.

**10:14 priya.raghunathan**
Good. Let's not lose the thread of what's actually true now, because we had thirty minutes there where the room believed two exceptions existed.

**10:16 marcus.lin**
Stepping away, payments-api standup. Back in 20.

**10:31 ola.ferrand**
Flaky-test noise unrelated to any of this: the badge-extractor integration suite went red on CI run 4471 with a truncated-payload assertion, then green on rerun 4472 with no changes. Third time this week it's done the truncated-payload flake. Filed REL-2209 to track, not blocking anything, we still don't know why it does that. Ignore unless it starts blocking releases.

**10:32 priya.raghunathan**
Noted, keep it on REL-2209, not in here. This channel is exceptions today.

**10:40 kenji.watanabe**
Question for the record while it's quiet. On the weekly review control for EX-14 — if the review finds a `k-legacy-2024` badge whose service is search-api, that's an incident now, yes? Because search-api has no exception. Whereas a payments-api one inside the window is expected.

**10:41 dana.whitfield**
Yes. Post-revocation, any `k-legacy-2024` badge that isn't payments-api-inside-the-window is an incident. payments-api-inside-the-window is the one and only covered case. A search-api badge signed with that key is unauthorized full stop, because EX-15 was denied.

**10:42 kenji.watanabe**
Perfect, that's what I needed for the checklist.

**11:15 kenji.watanabe**
Actually one more, updating our orders-api runbook. I'm writing the "keys and exceptions" section. So I should list: payments-api and search-api both hold exceptions through end of June for the legacy key, and —

**11:16 dana.whitfield**
Stop. No. That is wrong and it's exactly the kind of thing that becomes load-bearing in a runbook and then someone waves a search-api legacy badge through in July because "the runbook said they had an exception". search-api does NOT hold an exception. EX-15 was DENIED an hour and a half ago in this thread.

**11:17 kenji.watanabe**
Ugh, you're right, I read my own struck-out note back as if it were current. My mistake. Correcting.

**11:18 ruth.callahan**
Kenji I appreciate you writing it down but this is why we're being loud. Let me say it one more time so the runbook has a clean sentence to quote: only payments-api holds an exception. search-api's request, EX-15, was denied. There is exactly one service permitted to sign release badges with `k-legacy-2024` after the revocation, and it is payments-api, and only until `2026-06-30T00:00:00.000Z`.

**11:19 kenji.watanabe**
Copied that verbatim into the runbook. "Only payments-api holds an exception. EX-15 denied." No ambiguity this time.

**11:20 ingrid.solberg**
And note in the runbook that the payments-api exception is itself bounded to the instant. It is not "payments-api may use the legacy key." It is "payments-api may use it for statements issued strictly before `2026-06-30T00:00:00.000Z`." The scope has a service dimension and a time dimension and both are load-bearing. Drop either and the sentence is wrong.

**11:21 kenji.watanabe**
Both dimensions in. Service: payments-api only. Time: `issued_at < 2026-06-30T00:00:00.000Z`. Done.

**11:23 tomas.berg**
For release calendar hygiene — I've set the single note: "payments-api legacy-key sunset, boundary 2026-06-30T00:00:00.000Z, source EX-14 / SEC-3341." No search-api entry. If HSM provisioning clears earlier we retire it earlier, per control 4.

**11:24 marcus.lin**
Back. Confirmed the June 12 HSM projection with infra just now, so realistically we're off the legacy key well before the boundary. The exception is margin, not the plan, exactly like dana wanted it framed.

**11:25 dana.whitfield**
That's the right posture. The instant is a ceiling. If you're done June 12, you retire EX-14 June 12 and we stop carrying the risk two weeks early. Update SEC-3341 when you cut over so I can close the weekly review.

**11:26 marcus.lin**
Will do. I'll post the cutover badge digest here and on SEC-3341 the day it lands so there's a clean "last legacy-signed payments-api release" marker in the record.

**11:28 priya.raghunathan**
Good thread. Let me pin the two outcomes so nobody re-litigates at 2am: EX-14 granted, payments-api only, boundary `2026-06-30T00:00:00.000Z`. EX-15 denied, search-api, no exception. Anyone who tells you search-api has an exception is remembering the 09:49 version of this thread and needs to read to the end.

**11:29 yusuf.adeyemi**
Ha. Fair. HSM provisioning ticket for search-api is open, INFRA-5570, I'm in the queue behind payments-api. Onwards.

**11:30 ingrid.solberg**
Record is complete and consistent. One granted exception, one denied, one exact instant, both dimensions of scope written down. That is what an auditable exception looks like. I'm out.

**11:31 ruth.callahan**
Thanks all. Decisions stand. EX-14 granted for payments-api to `2026-06-30T00:00:00.000Z`; EX-15 denied for search-api. Closing the war room for today.
