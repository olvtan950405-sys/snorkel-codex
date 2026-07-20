# #war-room-releasesentinel — 2026-05-06

## 2026-05-06

**08:41 priya.raghunathan**
Morning. Spinning this up as its own thread because it's clogging the main channel. Symptom: ReleaseSentinel is flagging a pile of badges as `BRANCH_MISMATCH` — the `release_branch` in the attestation statement does not match what the repo says the tag was cut from. Overnight run flagged 6 across payments-api and orders-api. Two of them look genuinely wrong, the rest I can't tell yet. Need eyes.

**08:42 priya.raghunathan**
Not the crash thing. This is separate. The worker is up, extracting fine, signatures verify, keyring lookups succeed. It's purely the branch field disagreeing with `CHANGELOG.md`. Please keep the segfault conversation in the other channel — still don't know why on that one anyway.

**08:44 ola.ferrand**
Ack. So this is "the badge says X, the repo says Y, who's lying" not "the worker fell over". Good, I like problems that don't involve core dumps before coffee.

**08:46 priya.raghunathan**
Two concrete ones to anchor on, both payments-api. Case 1, tag `v8.4.0`. The badge's statement says:
```json
{"statement":{"artifact_digest":"sha256:9c1f...c40a",
              "issued_at":"2026-05-05T22:11:07.000Z",
              "key_id":"k-build-2026a",
              "release_branch":"release/9.0",
              "release_tag":"v8.4.0",
              "service":"payments-api"}}
```
`release/9.0`. On a `v8.4.0` tag. That is not a branch that even has a right to exist next to that tag as far as I know.

**08:47 priya.raghunathan**
Case 2, payments-api, tag `v8.4.1`. Statement says `release_branch: "release/8.4"`. But the changelog heading for that tag says it was cut from `hotfix/8.4.1`. So the badge and the changelog disagree by one branch.

**08:52 tomas.berg**
Pulling the repo to ground truth, I don't trust anyone's memory on this including mine. This is `git tag --list` from `/app/repo`, clean checkout, no local tags:
```
$ git tag --list
v8.2.1
v8.3.4
v8.4.0
v8.4.1
v8.5.0
```
Five tags. There is no `v9.0.0`, there is no `v9.0.0-rc`, nothing in the 9 line at all. So a badge claiming `release/9.0` on `v8.4.0` is claiming a branch that hasn't produced a single tag.

**08:53 tomas.berg**
And the log so you can see the shape of it:
```
$ git log --oneline --decorate -12
a1c9f4e (HEAD -> main) chore: bump dev version to 8.6.0-SNAPSHOT
7b2e881 (tag: v8.5.0, release/8.5) release: v8.5.0
6d0aa17 Merge branch 'release/8.5' into main
f3391cd (tag: v8.4.1, hotfix/8.4.1) release: v8.4.1 hotfix
90ab7c2 fix: null deref in settlement retry (#4471)
be55190 Merge branch 'hotfix/8.4.1'
c22d19b (tag: v8.4.0, release/8.4) release: v8.4.0
41f7de2 Merge branch 'release/8.4' into main
0e5a3aa (tag: v8.3.4, release/8.3) release: v8.3.4
88c1b20 (tag: v8.2.1, release/8.2) release: v8.2.1
2f4d6e9 seed: initial import
d0b1aab initial commit
```
Note what the decorations say. `v8.4.0` sits on `release/8.4`. `v8.4.1` sits on `hotfix/8.4.1`. Those decorations are the actual refs pointing at those commits. This is not a matter of opinion, it's where the tag object points.

**08:55 tomas.berg**
And the changelog, which I maintain by hand, matches the refs:
```
$ sed -n '1,40p' CHANGELOG.md
# Changelog

## v8.5.0 (release/8.5)
- search: new ranked suggest endpoint
- orders: idempotency keys on POST /orders

## v8.4.1 (hotfix/8.4.1)
- payments: null deref in settlement retry (#4471)

## v8.4.0 (release/8.4)
- payments: multi-currency settlement
- orders: partial refunds

## v8.3.4 (release/8.3)
- search: analyzer upgrade

## v8.2.1 (release/8.2)
- payments: fee rounding fix
```
So per the repo AND the changelog: `v8.4.0` = `release/8.4`, `v8.4.1` = `hotfix/8.4.1`. Both badges Priya pasted are wrong against ground truth. Case 1 badge says `release/9.0` — pure fiction. Case 2 badge says `release/8.4` — off by one, should be `hotfix/8.4.1`.

**08:56 priya.raghunathan**
Thank you. That's exactly the anchor I wanted. So now the question is what ReleaseSentinel is supposed to DO when the badge and the repo disagree, and — before that — which of them we treat as the source of truth. Because right now the worker is just yelling MISMATCH and dumping both into a triage queue and someone has to hand-adjudicate every one.

**08:57 marcus.lin**
Can I push back on the framing before we spend an hour on it. Case 1 (`release/9.0`) is obviously junk. But Case 2 is not a mismatch anyone should care about. The builder stamped `release/8.4` because the hotfix branch *forks from* `release/8.4`. The changelog says `hotfix/8.4.1` because Tomas types it in afterward. Those are two names for effectively the same lineage. Blocking a payments hotfix over that is exactly the kind of thing that makes people stop trusting the gate.

**08:58 tomas.berg**
They are not two names for the same thing. `hotfix/8.4.1` is a distinct branch with distinct commits that never touched `release/8.4`. `90ab7c2 fix: null deref` is on the hotfix branch. It is not on `release/8.4`. If it were on `release/8.4` I wouldn't have needed a hotfix branch.

**09:01 ola.ferrand**
Okay this is the real fork in the road so let me state it cleanly and then everyone can throw things. When the attestation's `release_branch` disagrees with what the repo says the tag was cut from, which one is authoritative?

Option A: **the attestation wins.** The builder stamped that field at build time, from the environment it actually built in. The changelog is written by hand, after the fact, and is chronically stale. The repo refs move. The badge is frozen at the instant of the build. If you want to know what got built, ask the thing that built it.

Option B: **the repo wins.** The changelog / tag decoration is the human-curated record of intent. The badge is just a claim, and a claim from a build environment we don't fully trust is not evidence about the repo.

**09:02 ola.ferrand**
I lean A, hard, and I'll say why. Half the "mismatches" in the queue are going to be the changelog lagging reality. Tomas is meticulous but he's one person and he edits that file after the release goes out, sometimes days after. The attestation is generated *during* the build from `git rev-parse` / the CI branch var. It is closer to the metal. Trusting a hand-edited markdown file over the machine-generated record feels backwards to me.

**09:03 marcus.lin**
+1 to A. And practically: if A is the rule, Case 2 stops being an incident. The badge says `release/8.4`, we accept that as what got built, done. Only Case 1 stays flagged, and that one we can chase down as a genuine anomaly.

**09:04 tomas.berg**
Strong disagree, and I want to be careful here because "the builder knows what it built" *sounds* airtight and it isn't.

**09:05 tomas.berg**
The builder knows what *directory it ran in*. It does not know the *meaning* of that directory. The `release_branch` field is populated by whatever the pipeline decides to stamp, and the pipeline's logic for that is not a law of physics, it's a shell script that someone wrote and that nobody audits. When that script is wrong, the badge is confidently, cryptographically-signed wrong. A signed lie is worse than an unsigned one because people stop checking.

**09:06 tomas.berg**
The repo, by contrast, is the thing the tag *is*. `v8.4.1` is a tag object that points at commit `f3391cd`. `f3391cd` is reachable from `hotfix/8.4.1` and is NOT the tip of `release/8.4`. That's not curation, that's the DAG. The changelog is my transcription of the DAG, and if my transcription is wrong you can catch me because the DAG is right there to check against. You cannot check the badge against anything except the badge.

**09:07 ola.ferrand**
> The changelog is my transcription of the DAG
Then why do we even store `release_branch` in the attestation. If the repo is authoritative we should just read the branch from the tag and never look at the badge field. Maybe that field exists because it was easy to stamp, not because it's trustworthy.

**09:09 dana.whitfield**
I've been reading and I want to put a security frame on this before we vote, because I think both A and B are being argued on *convenience* grounds and there's a threat-model question underneath that changes the answer.

**09:10 dana.whitfield**
The whole reason ReleaseSentinel exists is that we do not fully trust the build environment. The badge is a *claim made by the build*. The signature tells us the claim wasn't tampered with in transit. It does **not** tell us the claim is true. Those are different properties and people conflate them constantly.

**09:11 dana.whitfield**
So walk through the adversarial case. Suppose an attacker gets code execution in the build pipeline — precisely the supply-chain threat this system is built to catch. They build a malicious artifact. What `release_branch` do they stamp on it? Whatever they want. They stamp `release/8.4`, a nice trusted-looking branch, from inside the very environment that produces valid-looking badges. If our policy is "the attestation's branch field is authoritative," we have just told the attacker: you may self-certify your provenance. That is the field they most want to control and we'd be handing it to them.

**09:12 dana.whitfield**
Whereas if the *repo* is authoritative, the attacker's stamped branch is checked against a tag that they (hopefully) do not control. The check has teeth precisely because the two sources are independent. The moment you let the badge attest to its own provenance, you've collapsed two independent sources into one, and the one you kept is the one inside the blast radius.

**09:13 marcus.lin**
That's a real point but it proves too much. By that logic nothing the builder says can ever be trusted, including the artifact digest, which is also stamped by the builder. We trust the digest. Why is the branch different.

**09:14 dana.whitfield**
Because the digest is self-verifying and the branch isn't. I can hash the artifact myself and check it against the digest; if they disagree I know. The branch field has no such external check *unless we make the repo the external check*. `release_branch` is only as good as whatever we validate it against, and the only independent thing to validate it against is the repo.

**09:16 marcus.lin**
It's a nice theory. In practice the "independent" repo is a repo that the same CI system has write access to push tags into. If the attacker owns the build they can probably push a tag too.

**09:17 dana.whitfield**
"Probably" is carrying weight there. Pushing a tag is a different privilege than running a build step, and on a good day it goes through branch protection and a human. "Less independent than we'd like" is not the same as "as compromised as the badge." Defense in depth is exactly making the attacker clear two fences instead of one.

**09:18 priya.raghunathan**
I need to keep this moving because I have a backlog of 6 flagged badges and a compliance ask due Friday. Let me try to separate the two things being argued so we don't talk past each other.

**09:19 priya.raghunathan**
Thing 1: which source is authoritative for `release_branch` — the attestation field, or the repo/changelog.
Thing 2: what the worker DOES on mismatch — hard block, soft warn, queue for triage.

We're mostly arguing Thing 1. Thing 2 depends on Thing 1. Can we at least get a provisional lean on Thing 1 so the queue can drain, and mark it revisit-able.

**09:20 kenji.watanabe**
Late, catching up. Before you lean anywhere — has anyone actually looked at *why* Case 2 says `release/8.4`? Because I think it's not a bug and not an attack, I think it's the pipeline doing exactly what it was told, and that changes how much weight the field should carry.

**09:21 kenji.watanabe**
The hotfix pipeline is a different pipeline from the normal release pipeline. When we cut a hotfix, the job forks from the parent release branch — `hotfix/8.4.1` forks from `release/8.4` — and the branch-stamping step in that pipeline reads the *parent* release branch, not the hotfix branch it's actually on. So it stamps `release/8.4` for every `8.4.x` hotfix. It's not lying, it's stamping the lineage root instead of the working branch. Known quirk. It's been like that since we introduced hotfix branches.

**09:22 tomas.berg**
Yeah. I've complained about this before. The hotfix pipeline stamps the parent release branch, always. So `v8.4.1` will *always* come out of the builder saying `release/8.4` even though the tag lives on `hotfix/8.4.1`. That's not six random anomalies, that's a systematic offset baked into one pipeline.

**09:23 kenji.watanabe**
Right, and I want to flag it as *observation only*, I'm not proposing what to do about it. Just: if we're deciding whether the attestation field is authoritative, we should know that for the entire class of hotfix releases, that field is systematically stamped with the parent branch, by design, not by accident. Whatever we decide has to survive that fact.

**09:24 ola.ferrand**
That actually... cuts against my Option A a bit. If the field is "authoritative" but we know it's systematically wrong for every hotfix, then "authoritative" means "authoritatively reports the parent branch," which is not the same as "reports where the tag was cut from." Ugh.

**09:25 marcus.lin**
Or it cuts *for* A — the field is authoritative about what the builder built from, which for a hotfix is genuinely a descendant of `release/8.4`. The changelog choosing to call it `hotfix/8.4.1` is a naming convention. The builder's answer isn't wrong, it's answering a slightly different question.

**09:26 tomas.berg**
It is wrong. `hotfix/8.4.1` is where the commit lives. `release/8.4` is where it *forked from*. Those are different and the difference is the entire reason we have hotfix branches. Erase that distinction and you erase the reason the process exists.

**09:27 dana.whitfield**
And note this cuts my way too, sharply. If the hotfix pipeline *systematically* stamps a branch other than the true one, then "trust the attestation field" is a policy we already know produces wrong provenance for an entire release class. We'd be codifying "trust the field" while simultaneously knowing the field is by-design incorrect for hotfixes. That's not a policy, that's a footgun with a signature on it.

**09:29 dana.whitfield**
Agreed it's not the same *mechanism*. But from the worker's point of view, standing there holding a badge that says `release/8.4` on a `v8.4.1` tag, it cannot tell "boring hotfix pipeline quirk" apart from "attacker stamped a trusted branch." Both produce a badge whose branch field disagrees with the repo. That indistinguishability is exactly why I don't want the field to be authoritative. The field being authoritative means we wave through both.

**09:31 priya.raghunathan**
And there it is. That's the actual tension. Whatever we pick, one of these two hurts:
- Repo authoritative → every hotfix badge flags, forever, because the pipeline quirk guarantees it. Real toil, real alert fatigue.
- Attestation authoritative → we accept a field we know is by-design wrong for hotfixes and self-attested for everything, which Dana's threat model says is the field an attacker most wants.

Neither is free.

**09:32 yusuf.adeyemi**
morning all, scrolled up, this is a fun one. dumb question from search-api land: do we have any badge where the two sources *agree* that isn't a hotfix? like is normal-release-path clean and it's ONLY hotfixes plus the one `release/9.0` gremlin that mismatch?

**09:33 priya.raghunathan**
Good question. Let me actually pull the counts instead of guessing.

**09:35 priya.raghunathan**
Of the 6 flagged overnight:
```
tag       service        badge_branch     repo_branch      class
v8.4.1    payments-api   release/8.4      hotfix/8.4.1     hotfix-offset
v8.4.1    orders-api     release/8.4      hotfix/8.4.1     hotfix-offset
v8.4.0    payments-api   release/9.0      release/8.4      genuine-anomaly
v8.3.4    payments-api   release/8.3      release/8.3      ??? see below
v8.2.1    search-api     release/8.2      release/8.2      ??? see below
v8.5.0    orders-api     release/8.5      release/8.5      ??? see below
```
So 2 are the hotfix offset Kenji described. 1 is the `release/9.0` gremlin. And 3 of them the branches ACTUALLY MATCH and I have no idea why the worker flagged them. Those bottom three might be noise from the other bug or something in extraction. I'm pulling those out of this thread — if the strings are equal they shouldn't be here.

**09:36 ola.ferrand**
The bottom three matching-but-flagged ones smell like they're from the extraction instability, not from a real branch disagreement. Trailing null bytes in the decoded string, a `release/8.5 ` vs `release/8.5` kind of thing. I'll look, but not in this thread, that's the other channel.

**09:37 yusuf.adeyemi**
ok so the honest population is: 2 hotfix-offset, 1 real gremlin. everything else is a match or noise. much smaller fire than "6 mismatches" sounded.

**09:38 priya.raghunathan**
Correct, and thank you for making me count. So the policy question is really about 3 badges and one systematic class. Doesn't make it easier, but it lowers the temperature.

**09:39 marcus.lin**
So can we ship the pragmatic thing. Attestation authoritative. `release/9.0` still flags because there's no `9.0` anything in the repo to back it — so even under "attestation wins" you'd catch it, because a branch that produced zero tags is its own kind of anomaly. And the two hotfix ones stop being incidents. That's the outcome that drains the queue AND catches the real gremlin.

**09:40 tomas.berg**
That's not what "attestation authoritative" means though. If the attestation is authoritative, `release/9.0` IS authoritative and you *don't* get to flag it. You can't have "the badge wins, except when I don't like what the badge says." Either the field is trusted or it's checked against the repo. You're describing "repo checks the badge," which is Option B, you've just talked yourself into it while thinking you're in A.

**09:41 marcus.lin**
No — I'm saying trust the badge's branch, but separately flag "branch that has no corresponding tag." Those are two different checks.

**09:42 tomas.berg**
And what do you check "branch has no corresponding tag" against? The repo. You're back in the repo. There is no version of catching `release/9.0` that doesn't consult the repo, because the ONLY thing that tells you `release/9.0` is fictional is the absence of a tag on it, and the tags live in the repo. So the repo is in your trust path whether you admit it or not.

**09:43 ola.ferrand**
...he's right, annoyingly. My Option A doesn't actually catch Case 1 on its own. The only reason we *know* `release/9.0` is wrong is that we went to the repo and found no `9.0` tags. If we trusted the badge field we'd have shrugged and accepted `release/9.0`. The gremlin is only visible because we're already treating the repo as ground truth in our heads.

**09:45 dana.whitfield**
And that's telling. If the repo is your reference for detecting the anomaly, then the repo is your authority, and "the badge wins in the normal case" just means "we don't bother checking in the normal case," which is a policy of not-checking dressed up as a policy of trust.

**09:46 priya.raghunathan**
I want to be honest that we are not going to *settle* this today. Dana and Tomas have the stronger principled argument — repo authoritative, badge is a claim to be checked. Ola and Marcus have the stronger operational argument — the hotfix offset means "repo authoritative" flags a whole class forever and generates toil we can't staff.

**09:47 priya.raghunathan**
And the person who owns the branches and the changelog — Tomas — is about to go on leave for two weeks. I do not want to lock in "repo authoritative, flag every hotfix" and then have nobody around who can adjust the changelog or the pipeline if it turns into a firehose.

**09:48 tomas.berg**
For the record I think that's the wrong reason to pick the wrong answer. "The right person is on leave" is an argument for *waiting*, not for flipping the authority to the badge.

**09:49 priya.raghunathan**
Noted, and I don't disagree in principle. But I can't leave the worker dumping every hotfix into a triage queue that no one drains for two weeks either. That's how gates get switched off entirely, and then we have nothing.

**09:50 marcus.lin**
Payments has two more hotfixes likely this cycle. If each one lands in a manual triage queue and sits, that's real delivery pain and I will be escalating it.

**09:51 ola.ferrand**
Here's where I've actually landed, having argued myself partway across the aisle. I still lean toward treating the attestation's `release_branch` as the working authority — *provisionally* — but not for the "changelog is stale" reason I opened with. I lean that way because it's the state that keeps the gate on and the queue drainable while the hard question waits for Tomas. It is the less-correct answer that is more operable this fortnight. I don't love it.

**09:52 dana.whitfield**
I want it on the record that I think that's the wrong call and I'm only not blocking it because it's explicitly provisional. If this quietly becomes permanent because provisional decisions always do, I will reopen it. The field an attacker most wants to control should not be the field we declare authoritative, even for two weeks, even for convenience. Please someone write down that this is a temporary operational lean and not a security judgment.

**09:53 priya.raghunathan**
Understood, and fair. Let me write it down exactly like that so nobody can later claim it was decided.

**09:54 priya.raghunathan**
PROVISIONAL, to be revisited with tomas.berg on his return (est. 2026-05-19), not a settled policy:
- When the attestation's `release_branch` disagrees with what the repo says the tag was cut from, we lean toward treating the **attestation's `release_branch` as the working authority** for now, purely so the gate stays on and the triage queue drains while the real decision waits.
- This is an OPERATIONAL lean, explicitly NOT a security ruling. dana.whitfield dissents on threat-model grounds (a compromised build can stamp any branch it likes; the field an attacker most wants to control should not be self-certifying). tomas.berg dissents on correctness grounds (the repo/DAG is ground truth; the badge is a claim to be checked, not an oracle).
- Known unresolved quirk, recorded so we don't rediscover it: the **hotfix pipeline stamps the parent release branch, not the hotfix branch** (`v8.4.x` badges come out saying `release/8.4` even though the tag lives on `hotfix/8.4.x`). This is by-design in that pipeline, deterministic, and means the ENTIRE hotfix class will disagree with the changelog by this exact offset. No decision made on how to handle it. Flagging only.
- The `v8.4.0` → `release/9.0` badge is a separate genuine anomaly (a branch with zero tags in the repo). Not covered by the lean above. Chase separately under its own ticket.

**09:55 priya.raghunathan**
Filing the anomaly as REL-4192 (the `release/9.0` gremlin, payments-api v8.4.0). Filing the hotfix-offset observation as REL-4193 so it doesn't evaporate. The authority question itself I'm putting on the agenda for the 05-19 sync when Tomas is back, tagged SEC-2207 so Dana's dissent is attached to something.

**09:56 tomas.berg**
I'll take the REL-4193 write-up before I go so the hotfix-offset description is accurate and doesn't get mangled into "the pipeline is buggy" — it's not buggy, it does what it was configured to do, it's just configured to answer the wrong question.

**09:57 dana.whitfield**
And please make SEC-2207 say, in words, that the provisional lean is a stopgap chosen for operability and that security did not sign off on it. I want the audit trail to show it was flagged as contested, not blessed.

**09:58 ingrid.solberg**
Compliance lurking. For the audit trail I need one thing pinned down exactly: is 2026-05-19 a *hard* revisit date or aspirational? Because "provisional pending review" with no dated review is the kind of thing that gets us a finding. If it's the 19th, I'll log it as a committed review date and I'll chase it if it slips.

**09:59 priya.raghunathan**
Log it as committed: review on or before 2026-05-19, owner me, blocker is tomas.berg availability. If it slips you have my blessing to nag.

**10:00 ingrid.solberg**
Logged. review_committed=2026-05-19, status=provisional, contested=true, dissent_owners=[dana.whitfield, tomas.berg]. That's enough for me to defend it if anyone asks why the gate's behaviour changed this week.

**10:01 kenji.watanabe**
One more observation for REL-4193 before Tomas writes it, so it's captured accurately. The offset isn't just "hotfix stamps parent branch." It's specifically that the hotfix pipeline's branch-stamping step reads the branch it *forked from* at job-start, and forks always start from the parent `release/*`. So the value it stamps is deterministic given the tag: `v8.4.1` → `release/8.4`, `v8.5.2` → `release/8.5`, etc. Deterministic is the useful word. Whoever revisits this can compute the expected offset instead of eyeballing it. Not proposing they do — just: it's computable, not random.

**10:02 tomas.berg**
Good, that's exactly the framing I'll use. Deterministic, by-design, parent-branch-not-working-branch. I'll put the tag→stamped-branch mapping in the ticket so it's unambiguous.

**10:04 priya.raghunathan**
Yusuf, you're free. That search one's `release/8.2` vs `release/8.2`, equal strings, shouldn't have flagged. It's going to the other channel as suspected extraction noise, not a branch disagreement.

**10:06 marcus.lin**
So to be crystal clear on what happens to my hotfixes *this fortnight*: under the provisional lean, a `v8.4.x` badge that says `release/8.4` — which is what the hotfix pipeline always produces — does NOT get held in triage over the branch field. Yes?

**10:07 priya.raghunathan**
Under the provisional lean, yes — because we're leaning toward the attestation's branch being the working authority, so the badge saying `release/8.4` is taken at face value and the changelog disagreement doesn't hold it. That's the whole reason I'm accepting the lean, to unblock exactly that case. But it's provisional, it's contested, and it can be reversed on 05-19. Build to the possibility that it flips.

**10:08 marcus.lin**
Understood. Reversible. Thanks, that genuinely unblocks the cycle.

**10:09 dana.whitfield**
And to be crystal clear on MY side: taking the badge at face value for hotfixes is precisely the behaviour I'm objecting to — it's the exact behaviour an attacker would exploit, stamp a trusted `release/*`, get waved through. The only reason I'm tolerating it for two weeks is that it's dated, written down as contested, and owned. Remove any one of those three and I block.

**10:10 priya.raghunathan**
All three are in place. Dated (05-19), written as contested (SEC-2207, ingrid logged it), owned (me for the review, Tomas for the correctness view, you for the security view). If any of those slips, escalate and I'll back you.

**10:11 ola.ferrand**
For completeness on the tooling side: I'm NOT going to change any worker behaviour based on a provisional lean. The worker keeps emitting `BRANCH_MISMATCH` on disagreement exactly as it does now. What changes is how *triage* treats those events for the next two weeks — hotfix-offset events get closed as "provisional-accept per SEC-2207," `release/9.0`-class events get chased. No code change rides on a decision this soft.

**10:12 priya.raghunathan**
That's the right call. Nothing gets hardcoded off a provisional. Triage playbook change only, reversible, pointing at the ticket so the next person understands why.

**10:13 tomas.berg**
Last thing before I'm out. I want the record to reflect that I think we're going to look back at "attestation branch is authoritative" and wince. The repo is the thing the tag *is*. The badge is a thing the tag *claims*. When those disagree, the object beats the claim, that's just how provenance works. But I can't keep every hotfix in a queue for two weeks while I'm unreachable, so I'm not going to fight the operational lean. I'll fight it on the 19th, with the whiteboard, properly.

**10:14 dana.whitfield**
Seconded. Provisional accepted under protest. See you on the 19th.

**10:16 priya.raghunathan**
Recorded. Nobody's happy, which is about the right amount of happy for a provisional call. Where we actually are, for anyone arriving late: we did NOT decide which source is authoritative. We put a provisional operational lean toward the attestation's `release_branch` to keep the gate on and the queue moving, explicitly contested by security (Dana) and release-eng (Tomas), explicitly dated for revisit 2026-05-19 with Tomas back from leave (SEC-2207). Separately: `release/9.0` gremlin is REL-4192, real anomaly, chase it. Hotfix-offset is REL-4193, a known deterministic pipeline quirk (hotfix pipeline stamps the parent release branch, not the hotfix branch), recorded but not adjudicated. Three "matching but flagged" badges are extraction noise, not this thread. Closing this out as OPEN-provisional, not resolved.

**10:17 ingrid.solberg**
Perfect wording, thank you. That's auditable. status=OPEN-provisional, review=2026-05-19, no security sign-off recorded. I'm good.

**10:18 kenji.watanabe**
One nit for the record: let's not let REL-4193 get quietly closed as "won't fix / known quirk" before 05-19. The hotfix offset is the thing that makes the whole authority question hard. Keep it open and linked to SEC-2207.

**10:19 priya.raghunathan**
Linked. REL-4193 stays open, blocked-on SEC-2207, do-not-close. Good catch. Alright, I'm calling it. Thanks all. Tomas, enjoy the leave, we'll ruin your first day back with a whiteboard.

**10:20 tomas.berg**
Looking forward to it. The DAG doesn't move while I'm gone. Neither does my position.
