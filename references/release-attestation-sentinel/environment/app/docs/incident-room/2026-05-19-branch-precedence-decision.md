# #war-room-releasesentinel

## 2026-05-19

**08:41 tomas.berg**
Morning. Back as of today, laptop reimaged over the weekend so if I'm slow re-cloning bear with me. First thing I did was read up-thread and I want to reopen the branch question before it hardens into something we regret. The note from the 6th has ReleaseSentinel treating the attestation's `release_branch` as authoritative — i.e. whatever the badge says its branch is, that's what we record. I was on leave when that landed and nobody who actually owns the changelog was in the room. So: not settled. Reopening.

**08:42 tomas.berg**
To be clear I'm not accusing anyone of doing this behind my back. Half of you paged me on the 6th and I was literally on a ferry with no signal. But it's the kind of call that shouldn't be made without release eng and I'm release eng, so.

**08:44 priya.raghunathan**
Welcome back. Fair. But I want to timebox this. We reopened branch precedence twice already and every time it eats a morning. What specifically do you want to change and what's the blast radius.

**08:45 tomas.berg**
The change: the attestation should NOT be the thing that decides which branch a tag was cut from. `CHANGELOG.md` should. The heading `## <tag> (<branch>)` is the record of truth. Blast radius is small in terms of code, large in terms of "is our snapshot actually trustworthy". Give me twenty minutes to make the case properly, I've been thinking about it for a week.

**08:45 priya.raghunathan**
You have until standup. Go.

**08:49 tomas.berg**
Okay. Setup for anyone who wasn't deep in this. A badge carries a statement, and inside the statement there's a `release_branch` field. On the 6th the provisional leaning was: trust that field. The reasoning at the time — and it's not stupid — was that the build pipeline knows exactly which branch it built from, it's right there in CI, so who are we to second-guess it. The attestation is signed, so the field is signed, so it's tamper-evident. Ship it.

**08:50 tomas.berg**
Here's my problem with that. "The build knows which branch it built from" assumes the build is honest. The whole reason ReleaseSentinel exists is that we do NOT get to assume the build is honest. If we assumed honest builds we wouldn't be verifying anything, we'd just accept every badge and go home.

**08:51 ola.ferrand**
The worker would certainly be simpler if we just accepted everything. Fewer crashes too. (mostly kidding)

**08:51 ola.ferrand**
mostly.

**08:52 dana.whitfield**
Tomas this is exactly the hill I was trying to die on last week and I got outvoted by the "but it's signed" crowd, so I'm very glad you're back. Let me lay out the attacker argument in full because I think it's the whole ballgame and it didn't get a fair hearing on the 6th.

**08:56 dana.whitfield**
Consider what a signature over the statement actually buys you. It proves that whoever holds the signing key produced these exact bytes and they weren't altered in transit. That is genuinely valuable. What it does NOT prove is that the *contents* of those bytes are true. A signature is an integrity guarantee, not an honesty guarantee. If the party generating the statement is the same party asserting the field, then the field is self-asserted. The signature just means the liar signed their own lie legibly.

**08:57 dana.whitfield**
So now imagine a builder is compromised. Not a wild scenario — it's the threat we're paid to worry about. The builder still has a valid signing key, because compromise of the build host means compromise of whatever that host can sign with. The attacker builds an artifact off some branch of their choosing and writes `release_branch` to whatever string makes the badge sail through. They control the field AND the signature over it. There is no separation of duties. The attestation is adjudicating itself.

**08:58 dana.whitfield**
"The attestation adjudicates itself" is the sentence I want people to sit with. That's the failure. A document cannot be its own notary.

**09:00 marcus.lin**
I hear the theory but can we ground it. In practice our builders aren't compromised and the branch field has matched reality every single time I've looked. This feels like we're contorting the pipeline around a threat we've never actually seen.

**09:01 dana.whitfield**
"Never seen" is doing a lot of work there Marcus. We've never seen it because nobody's tried, or because it never happens? Those are different worlds and only one of them is fine. The point of a control is that it holds on the day the assumption breaks, not on the 364 days it doesn't.

**09:02 priya.raghunathan**
Marcus has a real point about grounding it though. Dana give me the concrete version. What does the attacker actually gain by lying about the branch specifically. Not branches in the abstract. This field.

**09:05 dana.whitfield**
Concretely: branch tells you the provenance lineage of the artifact — was this cut from a blessed release line, or from someone's `feature/pay-later-experiment` fork, or from an unreviewed personal branch. Downstream, a lot of trust flows from "this came off `release/8.4`". Promotion gates, who gets to deploy to prod, audit posture. If I'm an attacker who's built a poisoned artifact off a branch nobody reviewed, the single most useful lie I can tell is "this came off the release branch." It launders unreviewed code into the trusted lane. The branch field is precisely the lie worth telling.

**09:06 marcus.lin**
...okay that's a better example than I expected. Fine. I still don't love the operational cost but I withdraw "we've never seen it, so it can't matter."

**09:06 priya.raghunathan**
Noted and logged. Continue.

**09:07 tomas.berg**
So if the attestation can't be trusted to say which branch it came from, we need an *independent* source of that fact. Something the builder doesn't control. That's the changelog.

**09:08 kenji.watanabe**
Why is the changelog independent though. Genuine question. Isn't it also just a file in the repo that someone can edit?

**09:09 tomas.berg**
Good challenge. It's independent in the sense that matters: it's not produced by the build, it's produced by the release process, and it's under review. Every changelog heading lands via a PR that at least two humans look at. `## v8.4.0 (release/8.4)` doesn't appear because a builder emitted it — it appears because a release engineer cut the tag and recorded which branch they cut it from, and that record went through code review like everything else. A compromised builder cannot retroactively rewrite a merged, reviewed changelog heading without also compromising the repo and getting a malicious PR past review. That's a much bigger ask than flipping a field in a PNG you're already generating.

**09:10 kenji.watanabe**
That's the distinction I needed. The changelog raises the cost of the lie because it's got human review between the attacker and the record. The badge has nothing between the builder and the field. Got it.

**09:11 dana.whitfield**
Exactly Kenji. It's not that the changelog is unforgeable. Nothing is. It's that forging the changelog requires compromising a *different* control surface than the one you already own by owning the builder. We've moved the assertion out of the attacker's blast radius. That's the entire value.

**09:12 ola.ferrand**
So the shape of the rule is: for a given tag, go read `CHANGELOG.md`, find `## <tag> (<branch>)`, and THAT branch is the one we record in the snapshot. The badge's `release_branch` becomes... what, decoration?

**09:13 tomas.berg**
Not decoration. Evidence. We still read it, we just don't let it decide. We compare it against the changelog. The changelog is the source of truth for which branch a tag was cut from. The snapshot always records the branch the changelog names, never the one the badge claims. If they agree, lovely, no drama. If they disagree, that disagreement is itself a signal and we have to decide what to do with it.

**09:14 priya.raghunathan**
And "what to do with it" is where I predict the next hour goes. Let's have it. Default proposal on the table: mismatch = reject. Who's got a problem with that.

**09:15 yusuf.adeyemi**
just got here, scrolling. give me sixty seconds don't reject anything yet lol

**09:16 yusuf.adeyemi**
ok caught up. so the badge says branch X, the changelog says branch Y, X != Y, and the proposal is we reject the badge. what's the reject actually called in the output, a branch conflict?

**09:16 tomas.berg**
Yes. Call it a branch conflict. The badge is rejected as a branch conflict. It doesn't get accepted, it gets flagged, someone looks at why the story doesn't hang together.

**09:17 yusuf.adeyemi**
makes sense to me. if the two sources of truth for provenance disagree that's exactly the moment you want a human, not a rubber stamp.

**09:18 ingrid.solberg**
From a compliance standpoint I strongly prefer this to the 6th's version. An audit trail where provenance is asserted by the artifact itself is not an audit trail, it's a suggestion box. If the branch of record comes from a reviewed changelog and mismatches are surfaced as conflicts rather than silently absorbed, that's a defensible control. I'd want the exact term "branch conflict" used consistently in the output schema though, not "mismatch" in one place and "conflict" in another. Auditors hate synonyms.

**09:19 ingrid.solberg**
Also please, whatever we land on, write it down somewhere that isn't only this channel. I know, I know, I'm the compliance person and I'm asking for a document, groundbreaking.

**09:19 ola.ferrand**
The document is this channel Ingrid. Have you met us.

**09:20 priya.raghunathan**
Ingrid's right and Ola's also right and that's the tragedy of this team. Let's keep going and I'll worry about the write-up after.

**09:22 marcus.lin**
Okay hold on. Before we bless "mismatch = reject" as universal — there was a whole thing on the 6th about the hotfix pipeline behaving weird with branches. I don't remember the details because I checked out of that sub-thread, but I remember it being real and unresolved. If we reject every mismatch we might reject a bunch of legit hotfix badges. Can someone who was actually in that dig it up.

**09:23 tomas.berg**
Yeah. I need to introduce the wrinkle before we finalize because it directly bites the "reject all mismatches" line. This is the one carve-out I think we actually need, and I want it to be a deliberate, narrow carve-out and not a vibe.

**09:26 tomas.berg**
The hotfix pipeline has a known quirk. When it builds a hotfix, the badge it stamps records the *parent release branch* in `release_branch`, not the hotfix branch the tag was actually cut from. So for a hotfix tag like `v8.4.1`, the changelog correctly says `## v8.4.1 (hotfix/8.4.1)` — because that's the branch we cut it from, and I cut it, so I know — but the badge stamps `release/8.4`, the branch the hotfix branched off of. It's a pipeline bug in how the hotfix flow derives the branch label. Not malicious, just wrong, and it's been wrong for a while.

**09:27 kenji.watanabe**
So under "mismatch = reject" every single hotfix badge fails as a branch conflict, forever, until the pipeline is fixed. That's going to be a bad time.

**09:27 tomas.berg**
Correct. Which is why I want an explicit exception for exactly this case and nothing broader.

**09:28 ola.ferrand**
I want to register my objection now while it's cheap. The carve-out is ugly. We're about to write a rule that says "provenance disagreement means reject — except when it's this specific kind of disagreement that we've decided to forgive because our own pipeline is buggy." That's not a security policy, that's a shrug with extra steps. The correct fix is: fix the hotfix pipeline so it stamps the branch it actually built from. Then there's no mismatch and no carve-out and the rule stays clean.

**09:29 ola.ferrand**
I own the worker. I do not own the hotfix pipeline. But I'm going to be the one implementing the ugly special case in the worker, so I get to complain about it.

**09:30 tomas.berg**
You're not wrong that fixing the pipeline is the right end state. I'll own filing that. But I can't gate our branch policy on a pipeline fix that isn't scheduled and isn't mine to schedule either. We ship badges today that have this mismatch baked in, and rejecting all of them means we can't attest any hotfix, and hotfixes are by definition the releases we ship under pressure. We'd be breaking the most time-sensitive path to keep the rule pretty.

**09:31 marcus.lin**
+1 from payments. If a hotfix can't get through ReleaseSentinel then ReleaseSentinel is blocking the exact releases that exist because prod is on fire. That's the worst possible place to be strict.

**09:32 dana.whitfield**
I want to thread the needle here because I'm the one who just spent twenty minutes arguing that mismatches are dangerous, and now I'm going to argue that this particular mismatch is fine, and I don't want that to sound like I'm folding.

**09:36 dana.whitfield**
The reason the hotfix carve-out doesn't blow up my attacker argument: the thing that made the badge's branch field dangerous was that it could claim MORE trust than it deserves — laundering unreviewed code into the release lane by claiming `release/8.4`. Look at the hotfix quirk through that lens. The badge claims `release/8.4`. The changelog says `hotfix/8.4.1`. The badge is claiming the *parent release branch*, which is the more-trusted lineage, over the hotfix branch. So directionally it's the scary direction — the badge is claiming more provenance than the changelog grants.

**09:37 dana.whitfield**
BUT. And this is the load-bearing "but." We are not going to *record* the badge's claim. We never do, under Tomas's rule. The recorded branch is always the changelog's branch. So even when we forgive the hotfix badge, the snapshot says `hotfix/8.4.1`, because that's what the changelog says. The badge doesn't get to launder anything into the record. It just gets to not be rejected. Its lie — well, its bug — is noted and discarded, not propagated.

**09:38 dana.whitfield**
So the carve-out is narrow in exactly the way that keeps it safe: we tolerate the badge (we don't reject it), but we do not honor its branch claim (we still write the changelog's branch). The attacker's win condition was "get my false branch into the trusted record." That win condition is still closed. All we've relaxed is the reject, and only for the one shape of mismatch our own pipeline is known to produce.

**09:39 kenji.watanabe**
Let me make sure I have the mechanics exactly right because this is the kind of thing I'll be asked to reason about at 3am. The gate for the carve-out — what triggers "tolerate instead of reject" — is a property of the *changelog's* branch, right? Not the badge's?

**09:40 tomas.berg**
Yes, and that's the crucial detail, thank you for pinning it. The trigger is: the branch the changelog names for that tag begins with `hotfix/`. If the changelog's branch for the tag is a hotfix branch, a mismatch is tolerated and the badge is still accepted. If the changelog's branch is anything else, a mismatch is a branch conflict and the badge is rejected.

**09:41 tomas.berg**
It has to be keyed off the changelog branch, because the changelog is the thing we trust. If we keyed the carve-out off the badge's claimed branch, we'd be letting the untrusted document decide whether it gets to bypass the check. That would be insane. The trusted source decides everything, including whether the mismatch is forgivable.

**09:42 kenji.watanabe**
Right. So concretely the predicate is roughly "changelog branch for this tag startsWith `hotfix/`". Prefix match on the changelog side. Good. That I can implement without ambiguity.

**09:43 ola.ferrand**
Prefix, not exact. So `hotfix/8.4.1`, `hotfix/anything`, all hotfix branches get the tolerance, not just the one tag. Fine, that's the general shape of the quirk anyway — the whole hotfix flow has the bug, not one release.

**09:44 tomas.berg**
Correct. Any tag whose changelog branch starts with `hotfix/`. Let me do the worked example end to end because I want it unambiguous in the record.

**09:48 tomas.berg**
Worked example. Tag `v8.4.1`.
- Changelog heading: `## v8.4.1 (hotfix/8.4.1)`. So the changelog's branch for this tag is `hotfix/8.4.1`.
- The badge for `v8.4.1` has a statement with `release_branch` = `release/8.4`. (The parent release branch. The hotfix pipeline quirk.)
- Compare: badge says `release/8.4`, changelog says `hotfix/8.4.1`. They disagree. Mismatch.
- Is the changelog branch a hotfix branch? `hotfix/8.4.1` starts with `hotfix/`. Yes.
- Therefore: TOLERATED. The badge is accepted. Not a branch conflict.
- Recorded branch in the snapshot: `hotfix/8.4.1`. The changelog's branch. NOT `release/8.4`. We never record the badge's claim.

**09:49 tomas.berg**
So `v8.4.1` comes through as accepted, and the branch we write down is `hotfix/8.4.1`, and everyone's happy including Dana because nothing false made it into the record.

**09:49 dana.whitfield**
Confirmed. That example is exactly the safe case and I'm on board with it as written.

**09:50 yusuf.adeyemi**
just to be annoying — the recorded branch is hotfix/8.4.1 even though the badge we accepted literally says release/8.4. someone reading the snapshot might go "wait the badge said something else." is that going to confuse people.

**09:51 tomas.berg**
It might, briefly, and then they read the policy and understand that the changelog is authoritative and the badge's branch is only ever evidence. The snapshot reflects truth, not what the badge asserted. If anything the discrepancy in the badge is a breadcrumb pointing at the pipeline bug we still need to fix. It's a feature that they don't match — it's the tell.

**09:52 ingrid.solberg**
For audit I actually prefer that the recorded value can differ from the badge's asserted value, because it demonstrates the control is doing something. If the record just parroted the badge, an auditor would rightly ask why we bother reconciling at all. The fact that we can accept a badge and still overwrite its branch claim with the changelog's is the visible evidence of the reconciliation. Keep it.

**09:53 priya.raghunathan**
Okay. I want to force the obvious follow-up before someone asks it in three weeks and reopens this whole thing. Non-hotfix tag. Badge says branch X, changelog says branch Y, they mismatch, and Y does NOT start with `hotfix/`. What happens.

**09:53 tomas.berg**
Conflict. Rejected. Branch conflict. No tolerance. The carve-out is hotfix-only.

**09:54 priya.raghunathan**
Crisp. That's what I wanted on the record. Non-hotfix mismatch = branch conflict, rejected, full stop. The tolerance does not generalize.

**09:55 kenji.watanabe**
And to be exhaustive: a `release/` branch that mismatches — say the changelog says `release/8.5` and the badge says `release/8.4` — that's rejected, because `release/8.5` doesn't start with `hotfix/`. Even though both are "real" branches. Mismatch on a non-hotfix changelog branch is always a conflict.

**09:55 tomas.berg**
Yes. The nature of the two branches doesn't matter. The only question the tolerance asks is "does the changelog's branch for this tag start with `hotfix/`." If no, any mismatch is a conflict. If yes, the mismatch is forgiven and we accept.

**09:56 marcus.lin**
What about the happy path, no mismatch at all. Badge and changelog agree. That's just accepted, recorded branch = the agreed branch, nothing special.

**09:56 tomas.berg**
Right. Agreement is the boring case. Record the changelog's branch (which equals the badge's, since they agree) and move on. The interesting cases are only the disagreements.

**09:57 ola.ferrand**
Let me restate the whole thing in worker-implementer terms so I know I'm building the right machine, and you all correct me if I've got it wrong:
1. For each badge, get its tag. Look up `## <tag> (<branch>)` in `CHANGELOG.md`. That branch is `changelogBranch`. Snapshot's recorded branch is always `changelogBranch`.
2. Read the badge's `release_branch`, call it `badgeBranch`.
3. If `badgeBranch == changelogBranch`: fine, no conflict.
4. If they differ: if `changelogBranch` starts with `hotfix/`, tolerate — no conflict, badge still accepted. Otherwise, branch conflict, reject.
5. Either way the recorded branch stays `changelogBranch`.

**09:58 tomas.berg**
That is exactly it. Ship that machine.

**09:58 dana.whitfield**
That's a faithful statement of the policy and it preserves the security property. I approve it as written. The recorded branch is never the badge's, and the only relaxation is the reject, only for hotfix changelog branches.

**09:59 kenji.watanabe**
One nit on step 1 — if there's no `## <tag> (<branch>)` heading in the changelog at all, that's a different problem and not this thread's concern, right? That's the tag-existence question, separate policy.

**09:59 tomas.berg**
Correct, out of scope here. This thread assumes the tag resolves to a changelog heading. Whether a tag is even allowed to exist is a different rule owned elsewhere. Don't fold it into the branch logic.

**10:00 priya.raghunathan**
Good. That's the branch policy. Before I call it though I want to give Ola his objection its due, because he flagged the carve-out as ugly and I don't want to steamroll that just because we reached consensus on the mechanics.

**10:01 ola.ferrand**
Appreciated. My objection stands: the carve-out exists only because our hotfix pipeline stamps the wrong branch. That's a bug in a system we own. The clean world is: fix the pipeline, badge stamps `hotfix/8.4.1`, no mismatch, no exception, the rule is just "mismatch = conflict" with zero asterisks. Every asterisk in a security policy is a place a future person misreads it or an attacker probes it. I'd rather have zero.

**10:02 ola.ferrand**
I'm not blocking. I'm saying: log that this carve-out is compensating for our own defect, not for something inherent, and it should die the day the pipeline is fixed.

**10:03 ruth.callahan**
Reading in as the person who has to own the risk on this. I've been lurking since 09:30. Ola, you're right that it's ugly, and Dana, you're right that it's safe as scoped. Both things are true and I'm going to make the call on how we hold them together.

**10:06 ruth.callahan**
I'll accept the hotfix carve-out. It's a pragmatic, time-boxed call, not a principle. My reasoning: the security property Dana articulated is intact — we never record the badge's branch claim, so the carve-out cannot launder false provenance into the snapshot; all it does is decline to reject a mismatch that our own pipeline is known to manufacture. The residual risk is that an attacker producing a badge that claims `release/8.4` for a tag whose changelog says `hotfix/something` gets accepted rather than flagged. But even then the recorded branch is the hotfix branch, not the release branch they claimed, so they've gained nothing in the record. The exposure is "a bad badge isn't flagged as a conflict," not "a bad branch enters the trusted lane." I can carry that risk for a bounded period.

**10:07 ruth.callahan**
Time-boxed means: this carve-out is a compensating control for the hotfix pipeline defect, and it is expected to be retired when that defect is fixed. Tomas owns filing the pipeline fix. When the pipeline stamps the correct branch, we revisit and, I expect, delete the carve-out and go back to "mismatch = conflict" with no exceptions. Until then, the carve-out is the rule. It's real, it's in force, it's not optional for the implementation. Ola builds it as specified.

**10:08 ola.ferrand**
That's the right framing and I can live with it. Time-boxed compensating control, not a principle. I'll build it, and I'll be the first one cheering when we get to delete it.

**10:08 ruth.callahan**
For the record so nobody relitigates the scope: the tolerance applies if and only if the branch named in the changelog heading for that tag begins with `hotfix/`. Non-hotfix mismatch is a branch conflict and is rejected. The recorded branch is always the changelog's branch, hotfix or not, mismatch or not. That's the whole policy and it's final as of today.

**10:09 priya.raghunathan**
Calling it. Branch precedence, final, 2026-05-19:
The changelog heading is the source of truth for which branch a tag was cut from. This reverses the provisional leaning from the 6th that had the attestation's branch as authoritative — that's dead. The snapshot records the changelog's branch, never the badge's claim. Badge-vs-changelog mismatch is a branch conflict and the badge is rejected — except when the changelog's branch for that tag starts with `hotfix/`, in which case the mismatch is tolerated and the badge is accepted, and the recorded branch is still the changelog's hotfix branch. Non-hotfix mismatch: rejected. Everyone good?

**10:09 dana.whitfield**
Good.

**10:09 tomas.berg**
Good. And thank you for reopening it with me instead of telling me it was already decided.

**10:10 marcus.lin**
Good from payments. Hotfixes flow, that's what I needed.

**10:10 kenji.watanabe**
Good, mechanics are unambiguous.

**10:10 ola.ferrand**
Good, under protest, on the record, time-boxed. Building it.

**10:11 ingrid.solberg**
Good, and I'll take the language "branch conflict" as the canonical term for the rejected-mismatch case. Please don't let a synonym creep into the output schema.

**10:11 yusuf.adeyemi**
good, thumbs up, metaphorically, i know the no-emoji rule

**10:12 priya.raghunathan**
Reversal logged. Moving on. Ola, unrelated — the worker fell over again on the overnight batch, want to grab a thread for that separately? Not here.

**10:13 ola.ferrand**
Yeah. Different channel. That one's still a mystery, I've stared at it for three days and I still don't know why it dies where it dies. Not dragging that into a policy thread.

**10:13 priya.raghunathan**
Agreed, keep it out of here. This thread is the branch decision and I want it clean for whoever reads it back.

**10:14 tomas.berg**
One housekeeping thing so I don't forget: I'll file the pipeline-fix ticket for the hotfix branch-stamping quirk and link it here so the time-box has a home. REL to follow once I've re-authed my tracker after the reimage.

**10:15 ruth.callahan**
Please do, and reference this thread in it so the reviewer of that fix knows the carve-out is expected to be removed as part of closing it. That's how the time-box actually gets honored instead of living forever.

**10:16 tomas.berg**
Will do. And for the archive: the reason this took a morning and not five minutes is that Dana's attacker argument is the actual foundation, and it deserved to be stated in full rather than assumed. The rule is "changelog wins over the badge" and the reason is "a compromised builder can put any string in its own attestation, so the attestation cannot adjudicate itself." Everything else — the hotfix tolerance, the recorded-branch-is-always-the-changelog rule — falls out of that one principle. If a future reader only remembers one sentence, remember that one.

**10:17 dana.whitfield**
That's the sentence. The signature proves the bytes weren't altered. It does not prove the bytes are true. Provenance has to come from a source the builder doesn't control, and that source is the reviewed changelog. The rest is bookkeeping.

**10:18 yusuf.adeyemi**
saving that. ok i'm off, search-api has its own fires. thanks for catching me up twice.

**10:19 priya.raghunathan**
Thread's done. Branch precedence is final. Anybody who wants to reopen it needs a new fact, not a new opinion — we've done opinions.
