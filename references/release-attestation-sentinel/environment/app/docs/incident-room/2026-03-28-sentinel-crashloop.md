# #war-room-releasesentinel

## 2026-03-28

**08:41 priya.raghunathan**
Opening a war room. ReleaseSentinel in staging has been crashlooping since ~07:50. The `sentinel-worker` deployment in `staging-eu` is on its 14th restart. Pager went off at 07:58 (SENTINEL-WORKER-RESTART-STORM). Anyone already touching this before I start pulling logs.

**08:42 priya.raghunathan**
Dashboard: https://northwind.internal/grafana/d/sentinel-worker/overview?var-env=staging — restart count graph is a staircase. CPU spikes, flatlines, pod dies. Started clean, no deploy in the window I can see, last worker image push was 2026-03-25. It's only staging so nobody's bleeding, but staging feeds the pre-prod attestation gate and release eng have a v8.5.0 candidate they want through today. So it's not nothing.

**08:44 ola.ferrand**
Morning, I own the worker. Two minutes to get the crash logs off the node — the container filesystem gets wiped on restart so I have to grab the hs_err before the kubelet reaps it.

**08:47 tomas.berg**
Confirmed, I've got v8.5.0 sitting at the gate. Won't attest because the worker won't stay up long enough to process the queue. Blocked but not on fire. Yet.

**08:51 ola.ferrand**
Right, got one. Not a graceful exception, the JVM is going down hard. Top of the hs_err, `/var/log/sentinel/hs_err_pid1.log` from the pod that just died:

```
#
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x00007f3a9c0b41e7, pid=1, tid=44
#
# JRE version: OpenJDK Runtime Environment Temurin-21.0.6+7 (21.0.6+7) (build 21.0.6+7-LTS)
# Java VM: OpenJDK 64-Bit Server VM Temurin-21.0.6+7 (21.0.6+7-LTS, mixed mode, sharing, tiered, compressed oops, compressed class ptrs, g1 gc, linux-amd64)
# Problematic frame:
# C  [libatst_extract.so+0x41e7]
#
# No core dump will be written. Core dumps have been disabled.
#
# If you would like to submit a bug report, please visit:
#   https://github.com/adoptium/adoptium-support/issues
# The crash happened outside the Java Virtual Machine in native code.
# See problematic frame for where to report the bug.
#
```

**08:52 ola.ferrand**
So it's dying in the native extractor `libatst_extract.so`, the C library that reads the attestation chunks out of the badge PNG. Not in the JVM proper. That narrows *where* it dies. Says nothing yet about *why*.

**08:54 ola.ferrand**
"Outside the JVM in native code" means a normal Java stack trace won't help. But there's a native frame stack in the hs_err. Same file, continued:

```
Stack: [0x00007f3a72dfe000,0x00007f3a72eff000],  sp=0x00007f3a72efc9b0,  free space=1018k
Native frames: (J=compiled Java code, j=interpreted, Vv=VM code, C=native code)
C  [libatst_extract.so+0x41e7]  atst_read_chunk_payload+0x87
C  [libatst_extract.so+0x38b2]  atst_extract_statement+0x142
C  [libatst_extract.so+0x2a10]  atst_open_badge+0x2a0
J 2841  com.northwind.sentinel.native.ExtractorJNI.extractStatement([B)[B (0 bytes) @ 0x00007f3aa4c9f0ac
J 2840  com.northwind.sentinel.badge.BadgeReader.read(java.nio.file.Path) ...
j  com.northwind.sentinel.worker.AttestationWorker.processOne(...)+0x2c
v  ~StubRoutines::call_stub
V  [libjvm.so+0x8a1c3f]
```

**08:55 kenji.watanabe**
I've never actually looked at this worker. What is a "badge"? I own orders-api, I publish one on every release apparently, but to me it's just a step in the pipeline that goes green. What's actually in it.

**08:55 yusuf.adeyemi**
same. search-api emits one too. I assumed it was a QR code or something. it's a PNG?

**08:58 ola.ferrand**
OK, background, since a couple of you have never had reason to look.

A "badge" is a real PNG image. If you download one it renders — the little shield graphic on the release page, green shield, service name, tag. That part is cosmetic. The interesting part is hidden in the file.

PNG files are a sequence of "chunks": each has a length, a 4-letter type code, the data, and a CRC. There are the standard ones everyone knows — `IHDR` (header), `IDAT` (the pixels), `IEND` (end marker). But the format lets you add your own private chunks, and readers that don't recognise them just skip them. That's how the shield carries secret cargo and still opens in any image viewer.

**08:59 ola.ferrand**
Our cargo lives in a private chunk type `atSt`. Lowercase first letter = "ancillary" (not critical to render), lowercase third letter = "private" (ours, not a registered standard). So an image viewer sees `atSt`, shrugs, skips it, shows you the shield. Our extractor goes looking specifically for `atSt` chunks and pulls the bytes out.

**09:00 ola.ferrand**
Inside those `atSt` chunks is a JSON attestation:

```json
{
  "signature": "3n2Vb...base64 Ed25519 signature...==",
  "statement": {
    "artifact_digest": "sha256:9f2c...e1",
    "issued_at": "2026-03-25T06:11:00.000Z",
    "key_id": "k-build-2026a",
    "release_branch": "release/8.5",
    "release_tag": "v8.5.0",
    "service": "search-api"
  }
}
```

The `statement` is the claim: this artifact digest, from this branch, tagged this, for this service, issued at this time, signed under this key id. The `signature` is an Ed25519 signature over the statement. The worker's whole job: pull that JSON out, check the signature against a known public key, decide whether to trust the artifact.

**09:01 yusuf.adeyemi**
ok that's clever, hiding it in a chunk the viewer ignores. so where do the public keys come from

**09:02 ola.ferrand**
`/app/config/keyring.json`. A flat list of public keys, each with a `key_id` and base64 public key material, loaded at boot. When it reads a badge, it looks up `statement.key_id` in the keyring, gets the public key, verifies the Ed25519 signature over the statement bytes. If it checks out, the statement is authentic — really signed by whoever holds that private key.

**09:03 kenji.watanabe**
And "payload split across several chunks" — why would JSON be split? It's not that big.

**09:04 ola.ferrand**
Historical. The original badge writer capped `atSt` chunk data at a fixed size and just emits as many chunks as it needs, in order, then the extractor concatenates them back into one byte buffer before parsing the JSON. Most badges fit in a single `atSt` chunk. Some — longer branch names, or extra statement fields from newer pipeline versions — spill into two or three. It's *supposed* to be transparent: you reassemble the bytes and get the same JSON either way. I chose "supposed" on purpose.

**09:05 kenji.watanabe**
Noted.

**09:08 ola.ferrand**
So we're crashing inside `atst_read_chunk_payload`, which by the name reads the bytes out of one of those `atSt` chunks. That's the neighbourhood, not the crime. Let me get behaviour across a batch of badges rather than one crash — it's not crashing on *everything*.

**09:12 ola.ferrand**
Ran the extractor manually against the staging badge cache `/var/lib/sentinel/badges/`, 240 badges, outside the worker so a crash doesn't take down a pod. Results all over the place. Three buckets:

1. Extract clean and verify fine.
2. Crash the process hard — SIGSEGV, same `libatst_extract.so` frame.
3. DON'T crash but produce obviously wrong output — JSON comes back truncated or with trailing garbage tacked on.

Bucket 3 scares me more than the crashes honestly. A crash is loud. Garbage that parses is quiet.

**09:13 priya.raghunathan**
Show me bucket 3. What does "garbage" look like.

**09:14 ola.ferrand**
Badge for orders-api v8.4.1. This is what the extractor handed back before the JSON parser touched it:

```
{"signature":"kQ8vN2r0mZ4x...oT9g==","statement":{"artifact_digest":"sha256:11c4a9
```

That's it. Just stops, mid-value, mid-token. No closing brace, no closing quote. The parser downstream throws `Unexpected end of input at position 88` and the worker logs it as a bad badge — arguably the least-bad outcome, at least it's rejected.

**09:15 ola.ferrand**
Worse one. payments-api, multi-chunk. Extractor output:

```
{"signature":"7bQ...Lm==","statement":{"artifact_digest":"sha256:9f2c40e1","issued_at":"2026-03-25T06:11:00.000Z","key_id":"k-build-2026a","release_branch":"release/8.5","release_tag":"v8.5.0","service":"payments-api"}}\x00\x00\x1f\x8b\x08\x00...`\xc3\xd2^\x11atSt\x00\x00
```

The JSON is all there and looks complete — but then a run of null bytes and a chunk of binary that, look, that's `atSt` appearing again plus some gzip-looking header bytes. So the extractor overran the end of the statement and kept reading into whatever was sitting after it in memory. Good news: trailing junk usually makes the parser barf too. Bad news: "usually".

**09:16 kenji.watanabe**
"Usually" is doing a lot of work there. If the trailing garbage came after a syntactically complete JSON object, a lenient parser would just... take the first object and ignore the rest, wouldn't it?

**09:16 ola.ferrand**
It would. And I don't love that. But I'm not going to speculate about parser config in the middle of a war room. Let's stay on symptoms.

**09:17 dana.whitfield**
Coming in late, I own the keyring. Reading the scrollback now, want to see all three buckets before I say anything.

**09:19 tomas.berg**
While Dana reads — the pattern I keep half-seeing: single-chunk badges survive way more often than multi-chunk ones. My v8.5.0 candidate is multi-chunk and it's in the crash bucket every single time. The old v8.2.1 badge, tiny and single-chunk, extracts clean every time.

**09:20 yusuf.adeyemi**
oh interesting. so it's a size thing? the extractor chokes on big payloads?

**09:20 marcus.lin**
If it's just big multi-chunk badges, can't we make the badge writer stop splitting? Emit one fat chunk, then there's only ever one chunk to read and the crash goes away. I've got a payments-api hotfix that needs to attest today, I'd take a hack.

**09:21 ola.ferrand**
Slow down. "Single chunk survives, multi chunk dies" is a correlation I noticed too, but I've already got counterexamples in the data. Give me a second to pull them, I don't want us building a theory on 09:19's vibes.

**09:24 ola.ferrand**
Counterexamples, from the same 240-badge run:

- search-api v8.3.4: single `atSt` chunk, small. Clean. (fits)
- orders-api v8.4.1: single chunk. TRUNCATED (the first garbage example). (breaks it — single chunk, still wrong)
- payments-api v8.5.0: three chunks. Crashes. (fits)
- old search-api v8.2.1: two chunks. CLEAN. (breaks it — multi chunk, still fine)

So it is NOT simply "single = safe, multi = dies." Multi-chunk fail *more often*, but single-chunk fail too, and some multi-chunk are fine. Whatever's going on is more specific than chunk count.

**09:25 marcus.lin**
Damn. So my "just emit one chunk" idea doesn't necessarily save me.

**09:25 ola.ferrand**
Correct. Might reduce your odds. Might do nothing. I won't tell you it fixes it because I don't know that it does, and I'm not shipping a workaround built on a correlation I can already break.

**09:26 priya.raghunathan**
Pin the numbers so we stop hand-waving. Ola, of the 240:

**09:29 ola.ferrand**
Counted: 151 clean, 52 hard crash (SIGSEGV, native frame), 37 wrong output (truncated or trailing garbage). Of the 52 crashes: 44 multi-chunk, 8 single-chunk. Of the 37 wrong-output: 21 multi-chunk, 16 single-chunk. Of the 151 clean: 140 single-chunk, 11 multi-chunk. So multi-chunk is heavily over-represented in the two bad buckets, but not exclusively. The 8 single-chunk crashes and the 16 single-chunk garbage cases are the ones that kill the tidy theory.

**09:30 kenji.watanabe**
Those 8 single-chunk crashes are the interesting ones. If "it's a multi-chunk reassembly problem" were the whole story, those 8 shouldn't exist. Something about the individual chunk contents matters, not just how many there are. I'd stare at those 8.

**09:31 ola.ferrand**
Agreed those 8 are the tell. I've pulled them aside. I'm deliberately not going to eyeball-diff their bytes and announce a theory in chat — the last three theories here have each been dead by the next message. I'll dig properly, offline.

**09:32 dana.whitfield**
OK I've read it all. Two things.

First, symptom-side, I agree with Ola: do not ship a workaround off a correlation. "Emit one chunk" makes the failure rarer and therefore *harder to catch*, which is worse than a loud crash. A worker that reliably crashes reliably refuses to trust bad input. A worker that occasionally emits a truncated-but-parseable statement might occasionally trust the *wrong* input. I care much more about bucket 3 than bucket 2 for that reason.

**09:34 dana.whitfield**
Second thing, separate from the crash: going to look at the keyring made me realise I don't like what I see. `/app/config/keyring.json` is *only* public key material. The shape:

```json
{
  "keys": [
    {"key_id": "k-build-2026a", "public_key": "MCowBQYDK2VwAyEA...", "alg": "ed25519"},
    {"key_id": "k-build-2025b", "public_key": "MCowBQYDK2VwAyEA...", "alg": "ed25519"},
    {"key_id": "k-legacy-2024", "public_key": "MCowBQYDK2VwAyEA...", "alg": "ed25519"},
    {"key_id": "k-ci-sandbox",  "public_key": "MCowBQYDK2VwAyEA...", "alg": "ed25519"}
  ]
}
```

That's it. A key id, the bytes, the algorithm. Nothing in this file says which of these keys is *allowed* to sign a production release. No trust level. No "this key is sandbox only." No revocation flag. No expiry. Nothing.

**09:35 dana.whitfield**
Which means: if a badge shows up signed by `k-ci-sandbox`, or `k-legacy-2024`, and the signature is mathematically valid — the worker, as far as the keyring is concerned, has no basis to reject it. The keyring answers "is this signature real?" It does not answer "should this key be signing *this*?" Different questions, and only the first is written down anywhere.

**09:36 yusuf.adeyemi**
wait, `k-ci-sandbox` is in the production keyring? why

**09:37 dana.whitfield**
Because the sandbox pipeline verifies its own sandbox badges against the same keyring file, so the sandbox key has to be present for that to work. Fine for verifying-signature-is-real. Not fine if "present in the keyring" gets silently treated as "trusted to sign a real release." And right now, structurally, nothing distinguishes the two.

**09:38 kenji.watanabe**
So the policy — "which key may sign what" — isn't in the keyring at all. Where is it?

**09:39 dana.whitfield**
Exactly my complaint. As far as I can tell it isn't written down anywhere — it lives in people's heads and threads like this one. A problem I want on the record, but NOT today's fire, so I'm not going to solve it in the crash war room. Flagging it, moving on.

**09:40 priya.raghunathan**
Logged. Dana, open something separate for the keyring trust-metadata gap so it doesn't get buried under the crash. Different problem, different ticket.

**09:41 dana.whitfield**
Will do. Not resolving anything today, just making sure it isn't forgotten.

**09:42 ola.ferrand**
Back to the fire. The "garbage OR crashes" split isn't per-badge — the same badge does different things run to run, which is its own horrible clue. Same payments-api v8.5.0 badge, three consecutive runs:

```
$ ./atst-extract /var/lib/sentinel/badges/payments-api-v8.5.0.png
run 1: SIGSEGV (signal 11), frame atst_read_chunk_payload+0x87
run 2: {"signature":"7bQ...Lm==","statement":{"artifact_digest":"sha256:9f2c40e1","issued_at":"2026-03-25T06:11:00.000Z","key_id":"k-build-2026a","release_branch":"release/8.5\x00\x00\x00\x00\x00\x00\x00
run 3: {"signature":"7bQ...Lm==","statement":{"artifact_digest":"sha256:9f2c40e1","issued_at":"2026-03-25T06:11:00.000Z","key_id":"k-build-2026a","release_branch":"release/8.5","release_tag":"v8.5.0","service":"payments-api"}}
```

Run 1 crashes. Run 2 truncates and trails nulls. Run 3 is perfect. SAME input file, three different outcomes. Nothing about the badge changed between runs.

**09:43 priya.raghunathan**
That's non-deterministic. Same bytes in, three different behaviours out. Rules out "this specific badge is malformed" as the whole story — a malformed file would fail the same way every time.

**09:44 kenji.watanabe**
Non-determinism from identical input means the failure depends on something that isn't the input — process state, whatever happened to be in memory before it ran. That's a hint about the *class* of bug, but I'm not going to name it and Ola's already asked us not to.

**09:44 ola.ferrand**
Correct instinct, and correctly leaving it there. "Depends on something that isn't the input" is exactly as far as I'll let myself say out loud right now.

**09:45 yusuf.adeyemi**
so is run-to-run randomness why the pod crashloops? it gets a badge, sometimes crashes on it, restarts, picks up the same badge from the queue, sometimes crashes again...

**09:46 ola.ferrand**
That's consistent with what I see, yeah. The badge stays at the head of the queue because it never got marked done, so the restarted pod picks the same one up and flips the coin again. For the bad badges it mostly loses, and we get the staircase Priya posted at 08:42.

**09:47 priya.raghunathan**
So the queue head is a poison badge. Which one's at the head right now.

**09:48 ola.ferrand**
Checking the worker's queue offset... head of the staging attestation queue is `payments-api-v8.5.0.png`. The three-outcome one. Of course it is.

**09:49 priya.raghunathan**
Short-term, can we get the pod to stop dying so the rest of the queue drains? I don't care about attesting the poison badge right now, I care about the 200 badges behind it that are probably fine.

**09:50 ola.ferrand**
I can pull the poison badge out of the queue by hand to unblock the line — operational, not a fix, it just stops that one badge from repeatedly killing the pod. It does nothing about *why* it kills the pod. I can already feel this thread wanting to declare victory the moment the crashloop stops. Don't.

**09:51 priya.raghunathan**
Agreed. Unblocking the queue is not fixing the bug. Do the manual pull, note it in the incident log as mitigation only.

**09:54 ola.ferrand**
Pulled `payments-api-v8.5.0.png` off the head and requeued it to `/var/lib/sentinel/quarantine/` so we don't lose it and I can keep testing. Pod's been up 2 minutes without restarting, queue draining, restart count frozen at 61. Mitigation, not resolution. Say it with me.

**09:54 priya.raghunathan**
Mitigation, not resolution. Nobody closes anything.

**09:55 tomas.berg**
While the queue drains — different but related annoyance, and I want it on the record because it keeps biting me and it's going to matter when we eventually decide what's trustworthy. The changelog and the attestation don't always agree on what branch a tag came from.

**09:56 tomas.berg**
`CHANGELOG.md` in `/app/repo` has one heading per tag, and the heading names the branch it was cut from. Like:

```
## v8.5.0 (release/8.5)
## v8.4.1 (hotfix/8.4.1)
## v8.4.0 (release/8.4)
## v8.3.4 (release/8.3)
## v8.2.1 (release/8.2)
```

That's the release engineering source of truth for "which branch is this tag." Meanwhile the badge's own statement carries a `release_branch` field. Those two are supposed to match. They don't always.

**09:57 tomas.berg**
Example. v8.4.1 was a hotfix, cut from `hotfix/8.4.1` per the changelog. But I've seen a v8.4.1 badge whose statement says `"release_branch":"release/8.4"` — whoever built it branched-then-tagged in a way that recorded the parent release branch, not the hotfix branch. Neither is "wrong" exactly, just two different notions of "the branch," and they disagree.

**09:58 kenji.watanabe**
So if some future policy says "a tag is only trustworthy if its badge's branch matches the changelog's branch," v8.4.1 fails that check purely on a bookkeeping mismatch, not because anything's actually untrustworthy.

**09:58 tomas.berg**
Right. And I don't have a ruling on which one wins — the changelog heading or the statement field — and I'm not asking for one right now in the middle of a crash. I just want it written down that they can disagree, because someone downstream is going to assume they never do and get burned.

**09:59 dana.whitfield**
That's a real hazard and it compounds with my keyring gripe. Two separate places where "is this release legit" quietly depends on metadata nobody has defined the rules for: which key may sign, and which branch counts. Both assumed, neither defined. Not solving either today. Just noting they're both open.

**10:00 priya.raghunathan**
Both noted, both explicitly NOT being decided in this thread. Tomas, does the branch mismatch have anything to do with the crash?

**10:01 tomas.berg**
No, completely orthogonal as far as I can tell. The crash happens in the native extractor before anyone's comparing branches to anything. I brought it up because we're all here and it's the same general area of "things we trust about a badge." Separate annoyance, unresolved, I'll stop derailing.

**10:02 priya.raghunathan**
Back to the crash. Ola, where are we.

**10:05 ola.ferrand**
Where we are: three failure modes (clean / crash / garbage), proof it's non-deterministic on identical input, localised to `libatst_extract.so` and specifically the chunk-payload read path by the native frame name, and data showing multi-chunk badges fail far more often than single-chunk but single-chunk badges also fail. What I do NOT have is *why*. I'm not going to pretend the frame name plus a correlation equals a root cause. It doesn't.

**10:06 ola.ferrand**
Here's a fuller hs_err from one of the single-chunk crashes, since those break every theory and I want them documented properly. `/var/log/sentinel/hs_err_pid1_orders.log`:

```
# A fatal error has been detected by the Java Runtime Environment:
#
#  SIGSEGV (0xb) at pc=0x00007f3a9c0b41e7, pid=1, tid=51
#
# Problematic frame:
# C  [libatst_extract.so+0x41e7]  atst_read_chunk_payload+0x87
#
siginfo: si_signo: 11 (SIGSEGV), si_code: 1 (SEGV_MAPERR), si_addr: 0x00007f3a5c000000

Register to memory mapping:
RAX=0x00007f3a5bffffe0 is an unknown value
RBX=0x0000000000000e40 is an unknown value
RSI=0x00007f3a72efcb10 points into unknown readable memory
...
```

`SEGV_MAPERR` at an address that isn't mapped. That's all I'll characterise it as: it read from an address it shouldn't have. I won't speculate in this channel about how it came to hold that address — that's exactly the kind of guess this thread has been wrong about four times already.

**10:07 kenji.watanabe**
For the record: si_addr `0x7f3a5c000000` vs the buffer region around `0x7f3a72ef...` — far apart. Noting the observation, not drawing the conclusion. Symptom, not cause.

**10:07 ola.ferrand**
And even that I'd hold loosely. Addresses in an hs_err are a snapshot of one crash; the non-determinism means the next crash's could look totally different. One data point.

**10:08 priya.raghunathan**
OK. I want to timebox the "figure out why" because we've been at this two hours and the honest answer is we don't know yet. Ola, realistic estimate to actually understand this?

**10:09 ola.ferrand**
Not today. Native-code intermittent crash that depends on process state, on a library I'll need to rebuild with instrumentation and run under tooling I don't have wired into staging yet. Days, not hours. I won't give you a fake ETA. What I *can* commit to today: the mitigation holds the crashloop, poison badges are quarantined, and I write up the symptoms cleanly so whoever picks this up isn't starting from the scrollback.

**10:10 priya.raghunathan**
That's the honest answer, I'll take it. Let's get a ticket.

**10:12 priya.raghunathan**
Opened REL-2291: "ReleaseSentinel native extractor crashes / corrupts attestation payloads (staging)". https://northwind.internal/jira/browse/REL-2291

Summary as it stands, and I'm writing this as OPEN QUESTIONS not answers:
- worker crashloops in staging via SIGSEGV in `libatst_extract.so` (native), not the JVM
- three outcomes on extraction: clean / hard crash / wrong output (truncated or trailing garbage)
- non-deterministic: identical badge yields different outcomes across runs
- multi-chunk badges fail far more often than single-chunk, but single-chunk badges also crash and corrupt — NOT simply a chunk-count problem
- ROOT CAUSE: unknown. We still don't know why.
- mitigation only: poison badges manually quarantined to unblock the queue; does not fix anything

**10:13 ola.ferrand**
Accurate, and I appreciate "we still don't know why" being in writing. That's the true state.

**10:14 dana.whitfield**
Opened SEC-1188 for the keyring trust-metadata gap — no defined basis for which key may sign a production release — and linked it to REL-2291 as "related, not blocking." https://northwind.internal/jira/browse/SEC-1188 Separate from the crash, unresolved, not touching it further today.

**10:15 tomas.berg**
And note in REL-2291 that changelog branch vs statement `release_branch` can disagree (v8.4.1 is the live example). Not a cause of the crash. Just don't want it lost.

**10:15 priya.raghunathan**
Added both as linked notes. Neither is being decided here.

**10:16 marcus.lin**
So what do I tell my team about the payments-api hotfix that needs to attest today. It's behind a poison badge on a worker that crashes.

**10:17 ola.ferrand**
Your hotfix badge specifically — I haven't tested it. The badge blocking the queue is quarantined so the line's moving again. If yours extracts clean it'll attest; if it's one of the bad ones it'll fail or crash and we'll deal with it then. I can't promise which until it's tried, and I'm not going to give you a yes I don't have. That's how we end up trusting a garbage payload.

**10:18 marcus.lin**
That's not a yes.

**10:18 priya.raghunathan**
Marcus, if it comes to needing an exception on timing or trust, that's not mine to grant and it's not Ola's, that's a Ruth call and a separate conversation. Not today, not in this thread.

**10:19 marcus.lin**
Understood. I'll wait for the queue and escalate separately if I'm still blocked EOD.

**10:20 yusuf.adeyemi**
for what it's worth search-api's recent badges all extracted clean in Ola's run. small mercy.

**10:20 ola.ferrand**
"In that run" — remember the non-determinism. I wouldn't build anything on "search-api is fine."

**10:22 priya.raghunathan**
State as we pause: crashloop mitigated (poison badges quarantined), pod stable ~30 min. REL-2291 open, root cause UNKNOWN. SEC-1188 open (keyring trust metadata), unresolved. Branch/changelog disagreement noted in REL-2291, unresolved. No policy decided in this thread. v8.5.0 candidate still not attested. Downgrading from war room to a tracked incident on REL-2291. Ola drives the symptom write-up. We are explicitly NOT closing on a root cause because we do not have one.

**10:23 ola.ferrand**
Acknowledged. I'll attach the hs_err logs, the three-outcome reproduction and the bucket counts to REL-2291 tonight. One more time for the ticket-skimmers: we do not know why this happens. Everything today is symptoms and mitigation.

**10:24 kenji.watanabe**
One request for the write-up: keep the 8 single-chunk crashes and the 16 single-chunk garbage cases prominent. Those are the ones that kill the easy theories. Whoever debugs this should start there, not from the comfortable "it's just big multi-chunk badges" story that's technically the majority but explains nothing.

**10:25 ola.ferrand**
Agreed, front and centre. The easy theory is the trap.

**10:26 dana.whitfield**
Last thing and I'm out. Why I keep harping on bucket 3, the quiet garbage: a crash fails safe, it trusts nothing. A truncated-or-trailing-garbage payload that still happens to parse could fail *unsafe* — trust something it shouldn't. When we do eventually understand this, I want the security question ("could a corrupted extraction ever produce a payload we'd wrongly accept?") answered explicitly, not assumed away. Adding that as an open question on REL-2291.

**10:27 priya.raghunathan**
Good open question. Added. Still an open question, not an answer.

**10:28 priya.raghunathan**
Pausing the war room. Thanks all. REL-2291 is the home for follow-up. Root cause: unknown. We'll pick it up when Ola has instrumentation. Nobody declare this solved.

---

## 2026-03-29

**08:03 ola.ferrand**
Overnight note for the record, no resolution. Left the extractor looping against the full quarantine set on a scratch node — not the worker, a throwaway box — to gather more crash samples. 600 iterations across the 89 bad badges. Confirmed everything from yesterday and nothing new that explains it:

- still three outcomes, still non-deterministic on identical input
- one badge crashed 41 times out of 100 runs, produced garbage 22 times, extracted clean 37 times
- the register/`si_addr` values differ nearly every crash, consistent with yesterday's "it's a snapshot" caveat

More data. No cause. REL-2291 stays open.

**08:04 ola.ferrand**
Attached all 600 run logs to REL-2291 as `overnight-runs.tar.gz`. Stare at them if you like, but please don't post a theory here unless you can break your own counterexample first. We've all been wrong once in this thread already.

**08:31 kenji.watanabe**
Looked at a sample. Observation, not theory: crashes cluster on the same handful of badges but not deterministically, and the same badge appears in all three buckets across the 100 runs. That's all I can honestly say. Weird, and I don't know why either.

**08:40 priya.raghunathan**
Right. State hasn't changed: we can reproduce it, mitigate it, characterise it six ways, and still don't know why. REL-2291 remains open, root cause unknown. That's where I'm leaving it until we have real instrumentation on the native side.

**08:42 ola.ferrand**
Understood. I'll drive the instrumentation work separately and update REL-2291 when there's something real. Until then: symptoms documented, cause unknown, no fix, no policy decided. That's the thread.

**08:43 priya.raghunathan**
Closing the war-room channel here. Everything lives on REL-2291 now. Root cause: still unknown.
