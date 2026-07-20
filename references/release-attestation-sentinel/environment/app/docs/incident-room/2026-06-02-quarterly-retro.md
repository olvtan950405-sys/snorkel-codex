# #war-room-releasesentinel

## 2026-06-02

**09:31 priya.raghunathan**
Morning. This is the Q2 ReleaseSentinel retro thread. I know we usually do this on a call but half of us are in three timezones now and the last call was 45 minutes of people saying "you're on mute", so I'm running it async in here. Please actually type things.

**09:32 priya.raghunathan**
One ask before anything else. I want each of you to write down what we *actually decided* this quarter about the worker and the signing policy. Not what you think we decided, what we decided. Because right now the only record is this channel and about four other threads, and if any of us gets hit by a bus the next person is going to have to read six weeks of scrollback to learn that a sandbox-signed build is not a release.

**09:33 priya.raghunathan**
The point of writing it down is that it goes into a runbook. `https://northwind.internal/runbooks/releasesentinel` currently 404s. I would like it to not 404.

**09:34 tomas.berg**
It has 404'd since March. I filed REL-2104 to create the page. It is still open. It will be open at the heat death of the universe.

**09:34 priya.raghunathan**
Not with that attitude.

**09:35 ola.ferrand**
I will believe the runbook exists when I can open it and not before. Same energy as the Miro board.

**09:35 priya.raghunathan**
Don't get me started on the Miro board.

**09:36 dana.whitfield**
I'm happy to write the security half down properly. I've said in about four threads now that the keyring is public-key material only — `/app/config/keyring.json` tells you a key's bytes and nothing about whether that key is *allowed* to sign a release. Every time someone new joins they assume the keyring is the trust store and it is not. That belongs in the runbook in bold.

**09:37 dana.whitfield**
The trust policy lives in these conversations. Which is exactly Priya's point about the bus.

**09:38 ingrid.solberg**
From compliance side: the thing I need out of the runbook is the exact wording of the key expiry decisions, with the exact instants, because when the auditors come in Q3 they will ask "as of what timestamp did you stop trusting X" and "we sort of decided it in Slack" is not an answer I can give them. I have the instants written down separately. I am not going to paste them in a retro thread because retros get edited and I do not want a half-remembered version floating around.

**09:39 ingrid.solberg**
If you want the exact cutoff, it is in the thread where we made it. Read it there. Don't quote each other from memory.

**09:39 priya.raghunathan**
Noted and endorsed. Ingrid has the canonical dates, the threads have the reasoning, the runbook has neither because the runbook does not exist.

**09:41 marcus.lin**
Can we at least agree the retro covers: what broke, what we changed about the policy, and what's still on fire. Because "still on fire" is a long list and I have a payments release next week.

**09:42 priya.raghunathan**
Yes. Let's do it loosely. Start throwing things in. I'll try to herd it.

**09:43 kenji.watanabe**
I'll start with a question because I want to make sure I have it right before it goes in any runbook. The legacy key — `k-legacy-2024`, the one that got compromised in April — we revoked everything it ever signed, right? Like every artifact that key ever put its name on is now untrusted, retroactively, all the way back?

**09:44 kenji.watanabe**
I remember a very bad night where we were pulling badges and marking everything from that key as poison. Orders-api had two releases signed by it. I want to make sure I tell my team the right thing.

**09:45 yusuf.adeyemi**
oh man that night

**09:46 ola.ferrand**
The night the pager achieved sentience, yes

**09:47 priya.raghunathan**
Kenji hold that thought, Dana's going to want to answer it carefully and she's mid-coffee.

**09:48 tomas.berg**
While Dana caffeinates — I'll do the branch half, since that's mine and it's the one people get wrong the least, weirdly.

**09:49 tomas.berg**
The rule for which branch a tag belongs to: the changelog wins. `CHANGELOG.md` in `/app/repo` has one heading per tag and the heading names the branch it was cut from. `## v8.4.0 (release/8.4)`. If the badge's `statement.release_branch` disagrees with what the changelog says the tag was cut from, the changelog is authoritative and the badge is wrong. Not the other way around. The badge does not get to redefine history.

**09:50 tomas.berg**
People's instinct is to trust the signed statement because it's signed. But the signature only proves the statement wasn't tampered with. It doesn't prove the statement is *correct*. A build can correctly sign an incorrect branch. So: changelog wins.

**09:51 kenji.watanabe**
That one I actually have straight. Changelog is ground truth for branch, signature is ground truth for "nobody altered this JSON". Two different questions.

**09:52 tomas.berg**
Exactly. And before anyone asks: yes the hotfix thing is still a carve-out and yes it still annoys me. `v8.4.1` was cut from `hotfix/8.4.1` and it does not follow the same shape as the normal release/N branches, so it gets special handling. I'm not going to relitigate the exact shape of the carve-out in a retro, it's written up where we decided it. I just want it on record that I think it's ugly and one day it will bite someone who assumes every tag maps to a `release/*` branch.

**09:53 tomas.berg**
Existing tags for reference so nobody has to go digging: `v8.2.1 (release/8.2)`, `v8.3.4 (release/8.3)`, `v8.4.0 (release/8.4)`, `v8.4.1 (hotfix/8.4.1)`, `v8.5.0 (release/8.5)`. Five tags, four normal, one gremlin.

**09:54 priya.raghunathan**
The gremlin has a name and it is hotfix/8.4.1.

**09:55 ola.ferrand**
I want to nominate a different gremlin. The worker itself.

**09:56 ola.ferrand**
Status on the extractor for the retro: it still occasionally falls over on some badges. Not all of them, not reproducibly, not on any badge I can point at and say "this one, every time". Every couple of weeks a badge comes through and the worker just dies on it and the payload comes out garbage or truncated. REL-2291 is still open. It has been open the whole quarter.

**09:56 ola.ferrand**
Before anyone asks: no, I still don't know why. I have stared at it. I have added logging. It is not consistent enough to bisect. Some badges with split `atSt` chunks it eats fine, some it doesn't, and I can't yet tell you what's different about the ones it doesn't.

**09:57 priya.raghunathan**
How often is "occasionally"?

**09:57 ola.ferrand**
Maybe once every ten days I see the worker restart on a bad extraction. Sometimes it's a clean-ish garbage payload, sometimes it's a hard abort. I'll paste one.

**09:58 ola.ferrand**
```
[worker] 03:14:22.881 INFO  extracting attestation badge=v8.5.0-rc3.png chunks=atSt x4
[worker] 03:14:22.902 WARN  reassembled payload failed json parse at offset 611
[worker] 03:14:22.902 WARN  payload head: 7b227369676e6174757265223a2258...  tail: ...00 00 00 00 3f 3f 3f
[worker] 03:14:22.903 ERROR extractor returned non-zero, restarting worker
```
And a worse one from last week where it didn't even get to the parse, the JVM just aborted with a native crash. I'm not going to paste the whole hs_err, it's 900 lines and it does not tell me anything actionable. It happens down in the native extractor and then we're done.

**09:59 kenji.watanabe**
Is REL-2291 a data problem or a code problem?

**09:59 ola.ferrand**
If I knew that it wouldn't be open. Right now all I can honestly say in the retro is: symptom is the worker dies on certain badges, cause is unknown, it is not fixed, do not close the ticket. I'd rather have it open and honest than closed and wrong.

**10:00 priya.raghunathan**
Fine. REL-2291 stays open, marked unresolved, ola owns it. Moving on because I can see Dana typing a novel.

**10:03 dana.whitfield**
Okay. Kenji, your question, carefully, because this is exactly the kind of thing that ends up wrong in a runbook if we're sloppy.

**10:03 dana.whitfield**
No. We did not revoke everything the legacy key ever signed. That is the reversed decision. That's the thing we did on the first night in a panic and then walked back the next morning when everyone had slept.

**10:04 dana.whitfield**
On the first night, yes, the instinct was "the key is compromised, therefore nuke everything it ever touched, retroactively, all the way back." We literally started marking historical orders-api releases as poison. That is the night you're remembering. But retroactively distrusting every artifact a key ever signed means you also distrust a pile of releases that were signed legitimately, before the compromise, that were fine. That's not a security win, that's an availability outage you inflict on yourself.

**10:05 dana.whitfield**
So the next morning we walked it back. The rule we actually landed on is *not* "everything this key ever signed is dead." It's a rule based on **when the statement was issued** — the `issued_at` in the statement. There's a cutoff instant, and which side of it the statement's `issued_at` falls on is what matters, not the mere fact that the legacy key's name is on it.

**10:05 dana.whitfield**
I am deliberately not typing the exact instant here. Go read the thread from the 3rd — that's where we argued it out and that's where the exact cutoff is written down. Ingrid also has it. If you quote a cutoff to your team, quote it from that thread, not from me typing it half-awake in a retro.

**10:06 kenji.watanabe**
Ahh. Okay. So I have been telling people the wrong thing. I've been saying "anything from the legacy key is dead, full stop." That's the panic version.

**10:06 dana.whitfield**
That's the panic version, yes. It got reversed. The live rule is about the issued-at time relative to the cutoff. Please go re-read the thread from the 3rd before you brief your team, because I don't want you carrying my paraphrase either — read the source.

**10:07 kenji.watanabe**
Right. That's a genuinely important correction for me, thank you. Updating my notes. This is exactly the bus problem — I've been confidently wrong for weeks because the real decision only lives in one thread and I remembered the loud first-night version.

**10:08 priya.raghunathan**
This is the single best argument for the runbook that has ever been made in this channel and it was made by accident.

**10:08 dana.whitfield**
It's not an accident that it happened, it's an accident that we caught it. Kenji happened to ask out loud. How many people are running around with the panic version in their head and haven't said it out loud?

**10:09 marcus.lin**
Probably several. I'll poll payments quietly.

**10:10 ingrid.solberg**
And this is why I will not paste the instant into a retro. The instant is right, once, in one place, in the thread where we decided it. Every copy is a chance to introduce an error. Read the source.

**10:11 yusuf.adeyemi**
late to this as usual, sorry, was in the orders sync

**10:11 yusuf.adeyemi**
scrolling up

**10:13 yusuf.adeyemi**
ok while we're doing "write down what we decided" — for search-api I want it on record that we have an exception for the legacy key. search-api still validates a couple of old integrations that expect a badge signed by `k-legacy-2024`, and we got a carve-out so those aren't rejected. So the general "legacy key is not trusted after the cutoff" thing has a search-api hole in it. Wanted that in the retro so nobody's surprised.

**10:14 yusuf.adeyemi**
I'm pretty sure it was one of the EX tickets. EX-15 maybe? Ruth signed off on it. Anyway, point is search-api has an exception, please write that down.

**10:15 priya.raghunathan**
That's a big claim, an exception to the trust policy is exactly the kind of thing the runbook has to be precise about. Marcus you've been through the exception process most, does that match your memory?

**10:16 marcus.lin**
Hold on, let me pull the EX tickets. I've been living in that queue.

**10:16 kenji.watanabe**
While Marcus digs — do we even have a real list of granted exceptions anywhere? Because "I'm pretty sure it was EX-15" is precisely the failure mode we just caught me in.

**10:17 dana.whitfield**
There is no exception in the trust config, because there is no trust config, because the keyring is just public keys. Any exception is a policy decision that lives in a thread and ideally in an EX ticket that Ruth approved. So the EX tickets are the closest thing to a registry. Marcus, what does the queue actually say.

**10:19 marcus.lin**
Okay. Pulled it. Yusuf, I'm sorry but no. That is wrong and I want to be really clear about it because it's a security-relevant claim and it cannot go in a runbook.

**10:19 marcus.lin**
EX-15 is *yours* — it's the search-api request for exactly the carve-out you're describing, keep trusting `k-legacy-2024` for those old integrations past the cutoff. And it was **denied**. Ruth denied it. It's sitting in the queue right now with status Denied and Ruth's comment on it.

**10:20 marcus.lin**
```
EX-15  Requestor: yusuf.adeyemi (search-api)
       Summary: continue trusting k-legacy-2024 for legacy integration badges post-cutoff
       Status: DENIED
       Approver: ruth.callahan
       Comment: "Compromised key. No standing exception. Migrate the
                 integrations to k-build-2026a. Rejecting."
```

**10:20 marcus.lin**
So search-api does NOT have an exception. The request was made and it was refused. If anything search-api is *more* on the hook than average, because you have integrations still leaning on a compromised key and the migration off it is the actual open action item, not a granted carve-out.

**10:21 yusuf.adeyemi**
oh.

**10:21 yusuf.adeyemi**
oh no. I had that completely backwards. I remembered filing it and I remembered it being A Whole Thing with Ruth and my brain filed that under "sorted" instead of "denied."

**10:22 yusuf.adeyemi**
that's genuinely bad, I've been operating like we had cover. we do not have cover. sorry everyone. and thank god this came up in the retro and not in the audit.

**10:22 marcus.lin**
It happens. But yeah — do not tell anyone search-api has a legacy exception. It was requested, it was denied, the integrations still need to move. That's the real state.

**10:23 dana.whitfield**
For the record and for the eventual runbook: I'm not aware of *any* granted standing exception for `k-legacy-2024`. The only route to one is Ruth, and the one request that went in — EX-15 — was denied. So the policy is uniform: after the cutoff, legacy-key statements are not trusted, no carve-outs, and the exact cutoff is in the thread from the 3rd.

**10:24 ingrid.solberg**
I'm adding EX-15/DENIED to my audit file right now, because "an exception was requested and refused" is itself an auditable event and I'd rather have it logged than have someone later claim informal cover.

**10:24 yusuf.adeyemi**
please do, and put my name on the migration action item, it's mine to fix.

**10:25 priya.raghunathan**
This retro is doing more than any of our retros in a year and we are 50 minutes in. Two people just discovered they were confidently wrong about security policy. Keep going.

**10:26 ola.ferrand**
Fine, I'll be the third then, because I want to check my understanding of the sandbox key while we're in confessional mode.

**10:26 ola.ferrand**
Last month I flagged a release badge that came through signed by `k-ci-sandbox` and I called it a bad signature in the alert. I marked it as "signature verification failed / bad signature" and paged. Was that the right call? Because I've been treating sandbox-signed release badges as failed-signature cases.

**10:27 dana.whitfield**
No, and this is a distinction that matters enough that I want it crisp, because it's the kind of thing a runbook has to get exactly right.

**10:27 dana.whitfield**
The signature on that badge was **fine**. `k-ci-sandbox` is a real key, it's in the keyring, and it correctly signed the statement — the Ed25519 signature over the statement verifies. There is nothing wrong with the signature. Calling it a "bad signature" is wrong and it sends whoever's on call down completely the wrong path, looking for tampering that isn't there.

**10:28 dana.whitfield**
The problem is authority, not integrity. `k-ci-sandbox` is the sandbox pipeline's key. It has no authority to sign a *release*. It's in the keyring because the sandbox pipeline genuinely needs it there to do sandbox things. Being in the keyring means "we know this key's bytes," it does not mean "this key may authorize a production release." So a sandbox-signed release badge is a valid signature from a key with no release authority. Reject it — but reject it for the right reason.

**10:28 dana.whitfield**
"Bad signature" = someone tampered with or forged the JSON, go investigate a security incident. "Valid signature, unauthorized key" = the pipeline published a release from the wrong key, go yell at whoever wired sandbox into a release job. Totally different response. Don't conflate them.

**10:29 ola.ferrand**
Right, that's a clean distinction and I muddied it. The signature verified, the key just isn't allowed to bless a release. I'll fix the alert wording so it says "unauthorized signing key" and not "bad signature." Those page different people at 3am.

**10:29 dana.whitfield**
Exactly that. And this is the general shape of the whole policy, honestly: the keyring answers "is this key's signature genuine," the *policy in the threads* answers "is this key allowed to sign this thing." Two layers. Every mistake this quarter has been someone collapsing them into one.

**10:30 kenji.watanabe**
That's a really good one-liner. "Keyring proves genuine, policy proves allowed." Can that go in the runbook verbatim.

**10:30 priya.raghunathan**
It can go in the runbook the moment the runbook exists, which brings us neatly back to the runbook, which does not exist.

**10:31 tomas.berg**
I feel like we've established a pattern where every thread ends with "and this should be in the runbook" and then the runbook stays 404. At some point the archive *is* the runbook and we should just admit it.

**10:31 dana.whitfield**
The archive is a terrible runbook. You have to read six threads and know which loud early opinion got reversed. Kenji just demonstrated that failure mode live.

**10:32 tomas.berg**
I didn't say it was a good runbook. I said it's the runbook we have.

**10:33 priya.raghunathan**
Let me try to make the "write it down" thing concrete instead of aspirational. Action items. I'll list, you claim.

**10:34 priya.raghunathan**
1. Create the actual runbook page at the 404 URL. Draft skeleton at least.
2. Migrate search-api legacy integrations off `k-legacy-2024`.
3. REL-2291 — worker dies on some badges, unresolved, keep investigating.
4. Fix the sandbox-badge alert wording to "unauthorized signing key."
5. Someone confirm no other team has a panic-version understanding of the legacy cutoff.
6. Decide what to do about the Miro board that nobody can open.

**10:35 yusuf.adeyemi**
2 is mine. Search-api legacy migration. Already said it, saying it again so it's in the list.

**10:35 ola.ferrand**
3 is mine, obviously. And 4, I'll fix the alert this week, that one's small.

**10:36 priya.raghunathan**
Great. 1? Anyone? The runbook?

**10:37 priya.raghunathan**
...

**10:38 priya.raghunathan**
Anyone for 1.

**10:39 tomas.berg**
I have REL-2104 already open for the runbook page. I can... keep it open. I cannot promise to write it. Writing it means someone deciding what the canonical version of every decision is, and every time we try that we discover we disagree about a detail and the doc stalls.

**10:40 dana.whitfield**
I'll write the security section if someone else owns the branch/tag section and someone owns assembling it. I'm not going to be the sole owner because then it's my paraphrase and we just spent an hour establishing that paraphrases are how people end up confidently wrong.

**10:41 priya.raghunathan**
So 1 has no owner. Again. For the fourth quarter running.

**10:41 ola.ferrand**
The runbook is Schrödinger's document. It exists in every retro and in no filesystem.

**10:42 kenji.watanabe**
I'll take 5. I'll go around orders/payments/search and check who's carrying the panic version of the legacy rule vs the issued-at version. I already found one person: me. I bet I'm not alone.

**10:42 priya.raghunathan**
Thank you Kenji. 5 has an owner. 1 does not. 6 — the Miro board.

**10:43 ingrid.solberg**
What is even on the Miro board? I've never been able to open it. It asks me to log in with an account that doesn't exist.

**10:43 ola.ferrand**
Nobody knows what's on the Miro board. That's the thing. It was made in a workshop in Q1 by someone who has since left, under a personal account, and now it's a locked artifact we all reference and none of us have seen.

**10:44 tomas.berg**
It's cited in two Jira tickets as "see the Miro board for the diagram." The diagram is inaccessible. This is a metaphor for something.

**10:44 priya.raghunathan**
6 is "give up on the Miro board and redraw whatever was on it if we ever find out we needed it." No owner. Fine.

**10:45 marcus.lin**
Can I raise the meetings thing while we're doing process. We have too many standing meetings on ReleaseSentinel. There's this channel, there's the Tuesday sync, there's the security review that half overlaps, and there's the incident bridge that we keep leaving open. I'd like fewer.

**10:46 priya.raghunathan**
I'm sympathetic but the async retro is working *because* we do it in writing. If we cut meetings and don't replace them with written decisions in threads, we lose the archive, and the archive is the only reason Kenji found out he was wrong today.

**10:46 dana.whitfield**
Agreed. The problem isn't too many meetings, it's that the meetings don't leave a durable trace and the threads do. Kill the Tuesday sync, keep the threads. Every decision has to land in a thread whether or not it also happened in a call.

**10:47 marcus.lin**
I can live with "fewer meetings, more threads." Kill Tuesday sync, fold security review into this channel async, keep the incident bridge for actual incidents only.

**10:47 tomas.berg**
Motion to kill the Tuesday sync seconded with enthusiasm.

**10:48 priya.raghunathan**
Tuesday sync dies. Everyone gets 30 minutes back. Use them to not write the runbook, apparently.

**10:49 yusuf.adeyemi**
brutal

**10:50 priya.raghunathan**
While we're on people leaving — did everyone see that priyanka from the sandbox pipeline team is leaving end of month? She was the one who wired most of the CI signing. If anyone has questions about how `k-ci-sandbox` gets used in the pipeline, ask her in the next three weeks, because after that the knowledge walks out the door and we're reading git blame.

**10:51 dana.whitfield**
That's actually a concern for us specifically. If sandbox signing changes after she leaves and nobody documents it, ola's "unauthorized key" alerts could start firing for reasons none of us understand. Ola, might be worth a 30-min brain-dump with her before she goes.

**10:51 ola.ferrand**
Good call, I'll grab time with her this week. Add it to the list as item 7, mine, "extract sandbox-signing tribal knowledge from priyanka before EOM."

**10:52 priya.raghunathan**
7 added, ola owns. That's more owned action items than we usually manage.

**10:53 kenji.watanabe**
Can I do a sanity summary of just the corrections from today, not the whole policy, so people skimming later at least catch the reversals? I know we don't do neat summaries but I specifically mean "here's what people got wrong today."

**10:54 dana.whitfield**
Careful. I'd rather you not, honestly, and here's why. If you write "here's the corrected version" in a retro, someone reads *only* that, treats it as canonical, and we've recreated the exact problem — a paraphrase standing in for the source. The corrections in this thread point at where the real decisions live. That's on purpose. Point people at the source threads, don't re-summarize the source.

**10:55 kenji.watanabe**
Yeah, okay, that's fair. I'll just note *that* I was wrong and *where* the right answer lives, not restate the right answer. So: I had the legacy-key rule as the panic version, real rule is issued-at-relative-to-cutoff, cutoff and reasoning are in the thread from the 3rd, go read it there.

**10:55 dana.whitfield**
That I'm happy with. "I was wrong, here's the pointer" is safe. "Here's the tidy correct version" is how the next person gets it wrong.

**10:56 yusuf.adeyemi**
same for me: I claimed search-api had a legacy exception, it does not, EX-15 was denied, the real state is "migration owed," see the EX queue and the thread where the cutoff was set. I'm not going to restate the cutoff either.

**10:57 marcus.lin**
And I'll add: if anyone thinks they have an exception, check the EX queue for an actual DENIED/APPROVED from Ruth. "I remember filing it" is not "it was granted." Two people this quarter conflated those and one of them was a security carve-out.

**10:58 ola.ferrand**
And mine: sandbox-signed release badge is a valid signature from an unauthorized key. Not a bad signature. Different alert, different pager, different 3am. Fixing the wording.

**10:59 tomas.berg**
Mine's not a correction, mine's just still true: changelog wins over the badge for which branch a tag came from. The hotfix carve-out exists, it's ugly, its exact shape is in the thread where we decided it, go there. I refuse to retype it because if I retype it I'll get a detail wrong and prove Dana's whole point.

**11:00 priya.raghunathan**
This is the healthiest this channel has ever been about not trusting its own summaries. I'm weirdly proud.

**11:01 ingrid.solberg**
From my side the net of today for the audit file: one exception requested and denied (EX-15, search-api, legacy key), logged. One widespread misunderstanding of the legacy cutoff caught and being surveyed (Kenji, item 5). Alert-wording fix in flight so "unauthorized key" events don't get mislabeled as integrity failures. All good, auditable events. The exact instants stay in their source threads where I can cite them precisely.

**11:02 priya.raghunathan**
Let me try to close. Open and unresolved after today:

**11:03 priya.raghunathan**
REL-2291 — worker still dies on some badges, cause unknown, ola investigating, do not close.
REL-2104 — runbook page, still no owner, still 404, the eternal flame.
Search-api legacy migration — yusuf, real work, no exception backstopping it.
Sandbox alert wording — ola, small, this week.
Legacy-rule understanding survey — kenji.
Sandbox-signing knowledge transfer before priyanka leaves — ola.
Miro board — abandoned, nobody can open it, we've made peace.
Meeting load — Tuesday sync killed, decisions must land in threads.

**11:04 marcus.lin**
That's a real list. Half of it even has owners.

**11:04 tomas.berg**
The half without owners is the runbook. It's always the runbook.

**11:05 priya.raghunathan**
One day, Tomas. One day the URL will resolve and there will be a page and the page will say "the keyring proves genuine, the policy proves allowed" and Dana will have written it and we will weep.

**11:05 dana.whitfield**
I'll believe it when it 200s.

**11:06 ola.ferrand**
Right there with the Miro board and the runbook. The great inaccessible trinity: a board nobody can open, a runbook nobody wrote, and a worker nobody can explain. Q2 in three artifacts.

**11:07 priya.raghunathan**
On that note. Thanks everyone, this was genuinely useful, two live corrections and a killed meeting is a great retro. Please actually do your action items. The archive remembers even when we don't.

**11:08 yusuf.adeyemi**
going to go re-read the thread from the 3rd right now before I embarrass myself further, thanks all

**11:08 kenji.watanabe**
same. reading the source. no more paraphrasing from memory.

**11:09 dana.whitfield**
That sentence, "reading the source, no more paraphrasing from memory," is the whole runbook. If nothing else survives from today, that does.
