# #war-room-releasesentinel

## 2026-05-25

**08:58 ingrid.solberg**
Morning. I have an audit-tooling problem and I need whoever owns the snapshot writer awake before the auditors' 11:00 call. This is SEC-4821. Short version: the same badge directory, scanned twice, produced two different snapshot files, and the auditors' diff tooling flagged it as a change. It is a false positive but it is now a documented finding and I am the one who has to answer for it.

**08:59 ingrid.solberg**
Longer version for the record. The external audit team treats every snapshot the worker writes as an evidence document. They ingest it into `provctl` (the auditor CLI, their side, not ours), and `provctl` records the SHA-256 of the file it ingested. In their report a snapshot is *cited by that hash*. So when the hash of "the same evidence" changes between two runs, from their chair that is indistinguishable from tampering. They don't care about our intentions, they care that the bytes moved.

**09:01 priya.raghunathan**
Define "same badge directory" precisely before we spiral. Same host? Same run of the worker, or two separate invocations?

**09:02 ingrid.solberg**
Two separate invocations. One ran last night on the audit host as part of their nightly, one I ran this morning on my laptop after pulling the exact same directory off the share. Input is `/app/var/badges/2026-05-24/`, 44 badges, byte-identical on both machines — I checksummed the whole tree, the inputs are the same. Nothing was re-published, nothing re-signed. The only thing that differs is the snapshot the worker emitted.

**09:03 priya.raghunathan**
So the inputs are frozen and the output moves. That's the worst kind of nondeterminism. Paste the diff.

**09:04 ingrid.solberg**
Here's what the auditors sent me. This is their `provctl diff` between the two snapshot files, with their pretty-printer on so it's legible. Left is the audit-host run, right is my laptop run:

```diff
--- snapshot.audit-host.2026-05-24.json
+++ snapshot.laptop.2026-05-24.json
@@ -1,9 +1,9 @@
-{"generated_at":"2026-05-24T23:14:07Z","host":"audit-nightly-01","badge_dir":"/app/var/badges/2026-05-24",
-"badges":[{"service":"orders-api","status":"trusted","artifact_digest":"sha256:9f2c7a...d41b","release_tag":"v8.4.1"},
-{"service":"payments-api","status":"trusted","artifact_digest":"sha256:1ad0e3...77c9","release_tag":"v8.4.0"},
-{"service":"search-api","status":"unverifiable","artifact_digest":"sha256:5b8810...02ef","release_tag":"v8.5.0"},
-{"service":"orders-api","status":"rejected","artifact_digest":"sha256:c14f77...9a3d","release_tag":"v8.3.4"}],
-"counts":{"trusted":41,"rejected":2,"unverifiable":1}}
+{"generated_at": "2026-05-25T07:41:52+02:00", "host": "ingrid-x1", "badge_dir": "/app/var/badges/2026-05-24",
+"badges": [{"artifact_digest": "sha256:1ad0e3...77c9", "release_tag": "v8.4.0", "service": "payments-api", "status": "trusted"},
+{"artifact_digest": "sha256:5b8810...02ef", "release_tag": "v8.5.0", "service": "search-api", "status": "unverifiable"},
+{"artifact_digest": "sha256:9f2c7a...d41b", "release_tag": "v8.4.1", "service": "orders-api", "status": "trusted"},
+{"artifact_digest": "sha256:c14f77...9a3d", "release_tag": "v8.3.4", "service": "orders-api", "status": "rejected"}],
+"counts": {"rejected": 2, "trusted": 41, "unverifiable": 1}}
```

**09:05 ingrid.solberg**
Every badge is the same badge. Same digests, same statuses, same counts. But `provctl` scores it as a full-file change because effectively every line differs.

**09:07 ola.ferrand**
Right, so before anyone panics: nothing is wrong with the *evidence*. Look at what actually moved. Three separate things are jittering here and they're getting conflated.

**09:08 ola.ferrand**
One: the object keys within each badge are in a different order. Audit host wrote `service, status, artifact_digest, release_tag`; your laptop wrote them alphabetical. Two: the badge array itself is in a different order — orders-api/v8.4.1 was first on one run and third on the other. Three: whitespace. The audit host emitted `"badges":[` with no spaces, your run emitted `"badges": [` with a space after every colon. And separately, `generated_at` and `host` are genuinely different because they *are* different — different clock, different machine. That last one isn't a bug, that's just... true.

**09:09 priya.raghunathan**
So four sources of drift. Three are cosmetic, one is real metadata. None of them change the meaning of the document.

**09:10 ola.ferrand**
Correct. But `provctl` is a byte differ. It doesn't know "cosmetic". A colon with a space next to it is, to a hash, a completely different document. This is not the auditors being dense — a hash *should* change if the bytes change. The problem is on our side: we're emitting bytes that carry no information but still move.

**09:11 kenji.watanabe**
Why does the key order change at all between two runs of the same binary? That's the part that bothers me. Whitespace I can imagine being a config flag. But field order flipping run to run smells like we're serialising from something unordered and just taking whatever order the iterator hands us that day.

**09:12 ola.ferrand**
That's exactly what it is and I'm not going to stand here and pretend the writer promises an order today, because it doesn't. I'm not going to open that patch in this thread either — this thread is about what "correct output" has to *look* like, and then I'll go make the writer produce that. If we argue about the internals now we'll never agree on the spec. Let's nail the spec.

**09:13 priya.raghunathan**
Agreed. Spec first. Ingrid, from the auditors' side, what does "reproducible" have to mean for them to accept it? Give me their actual requirement, not a vibe.

**09:15 ingrid.solberg**
Their requirement is literally: "identical logical input MUST produce byte-identical output, such that the document may be cited by digest." That's the sentence from their controls doc. So we need a *canonical* form. Same inputs in, same bytes out, on any machine, any run, forever. If we can promise that, the hash becomes a stable citation and the false-positive findings stop.

**09:16 dana.whitfield**
I want to slow down on the word "canonical" because it gets thrown around and means five different things to five people. If we're going to commit to this in a controls response we should write down exactly what we mean, and it should be boring and mechanical and leave nothing to taste. Let me start a list and people can shoot at it.

**09:18 dana.whitfield**
Canonical snapshot, first draft of the properties I think are non-negotiable:
(a) Object member keys are emitted in a fixed, deterministic order. Sorted works and sorting is the least arguable rule because there's exactly one sorted order and nobody has to remember an insertion convention.
(b) No insignificant whitespace. No space after colons, no space after commas, no newlines between elements, no trailing newline drama. The only whitespace that survives is whitespace *inside* a string value because that's data.
(c) Encoding is fixed. UTF-8, no BOM, and escaping has to be consistent — the same character must always be written the same way, or we're right back here arguing about whether `/` got escaped.
(d) The badge list has a stable, defined order that does not depend on directory read order or filesystem or timestamps.
(e) There is a digest published over the canonical bytes, so a snapshot can be named by its hash in an audit report.

**09:19 kenji.watanabe**
(a) — sorted by what, exactly? Byte order of the UTF-8-encoded key, or some locale-aware collation? Because if anyone says "alphabetical" without saying which alphabet I'm going to lose it. Locale-aware sorting is how you get a snapshot that's canonical in Oslo and non-canonical in Tokyo.

**09:20 dana.whitfield**
Byte order of the encoded key. Code-unit / byte comparison, not collation. No locale anywhere near this. Good catch, that's exactly the kind of thing that would pass every test on our machines and then blow up on theirs.

**09:21 ola.ferrand**
Seconded, and the same discipline has to apply to (d). "Stable order for the badges" cannot mean "the order the directory listing happened to come back in", because directory iteration order is a filesystem lie — it differs between ext4 and whatever the audit host runs and it differs after a restore. It has to be an order we *compute* from the badge contents. Sort the badges by something intrinsic and total. The artifact digest is intrinsic to each badge and there's only one of each, so that's a natural sort key. Point is: derived from the content, not from the disk.

**09:22 kenji.watanabe**
As long as the sort key is guaranteed unique. If two badges could ever share the same sort key you've reintroduced nondeterminism at the tie. Digest is fine because two distinct artifacts don't collide, but whatever we pick has to be total or we're back here in a month.

**09:23 priya.raghunathan**
Fine. Sorted keys by byte order, badge list sorted by artifact digest, no locale, minimal whitespace, UTF-8 no BOM. That's most of Dana's list. Now the two fights I can see coming. Fight one: pretty-printing.

**09:24 marcus.lin**
I'll take the unpopular side then. These snapshots are unreadable. That diff Ingrid pasted is a wall. When payments has an incident at 2am and I'm staring at a snapshot trying to find my service, I want it indented, one badge per line, sorted so I can eyeball it. Can we please just pretty-print the thing.

**09:25 dana.whitfield**
No, and I feel strongly about this one. The moment you pretty-print you've reintroduced insignificant whitespace as a first-class citizen of the file, and that's precisely the thing that just cost Ingrid a finding. Two pretty-printers do not agree — tabs vs spaces, two-space vs four, space-before-colon, trailing newline, how they wrap arrays. The instant a formatter version bumps, every hash in every historical audit report is invalidated. The canonical form has to have no aesthetic degrees of freedom, because every degree of freedom is a future divergence.

**09:26 marcus.lin**
So I'm stuck reading minified JSON forever.

**09:26 ola.ferrand**
On disk, yes. Nobody said you read it raw. `provctl` pretty-printed it for the diff Ingrid pasted — the reader pretties it. Pipe it through `jq .`, whatever, at read time. Formatting is a *view* concern. The stored artifact is canonical and ugly and that is the whole point. Render it pretty when a human looks; never store it pretty.

**09:27 marcus.lin**
Fine. Grudgingly fine. Store ugly, read pretty. I still think it's user-hostile but I'm outvoted and I hear the tamper argument.

**09:28 priya.raghunathan**
Good, that's fight one. Ingrid does that satisfy the auditors — canonical stored, pretty only at read?

**09:29 ingrid.solberg**
Yes. They diff and hash the stored file. What we render for humans is our business. They actively do not want us storing a formatted file, because a formatted evidence document is one they have to normalise before hashing and they don't trust normalisers they didn't write. Ugly-canonical is what they're asking for.

**09:31 yusuf.adeyemi**
morning, catching up, read the scrollback. genuine question before you all lock it in: has anyone considered just emitting these as YAML? it's readable *and* compact, you get comments so we could annotate the badge list, block style is one-per-line so marcus gets his eyeball view for free. seems like it solves both sides.

**09:32 kenji.watanabe**
Oh no.

**09:32 ola.ferrand**
Yusuf I love you but no. YAML has no canonical form — that's not an opinion, the spec doesn't define one. Anchors, aliases, flow vs block, quoted vs unquoted, and different emitters disagree about all of it. It is strictly *worse* for reproducibility than the JSON we already have.

**09:33 dana.whitfield**
And the type coercion. Half our release tags and statuses are the kind of bare token YAML loves to reinterpret. `unverifiable` is fine but the day a value is `no` or `off` or `yes`, an unquoted YAML loader turns it into a boolean. The Norway problem — the country code `NO` parsing as false — is a real bug that has bitten real pipelines. We are trying to *reduce* the number of ways bytes can betray us and Yusuf just proposed the format with the most.

**09:33 yusuf.adeyemi**
ok ok, withdrawn. forget i said the four letters.

**09:34 priya.raghunathan**
Let it die. JSON, canonical, minified. Fight two, and this is the one I actually care about because it's not cosmetic. The digest. What does the hash cover — the whole file, or just the badge list?

**09:36 dana.whitfield**
This is the real question and I don't have a clean answer yet, so let me lay out the tension. Ingrid's whole ask is "cite the snapshot by its hash." Simplest thing: hash the entire canonical file, publish that. One document, one hash, done. But look back at the diff — `generated_at` and `host` are *in* the file and they legitimately differ every single run. If the hash covers the whole file, the hash moves every run *by design*, and we're right back to a moving citation even after we've canonicalised everything else. So "hash the whole file" defeats the purpose the moment there's a timestamp in the file.

**09:37 kenji.watanabe**
Right. The volatile metadata poisons the whole-file hash. So either the metadata comes out of the file, or the hash covers less than the file.

**09:38 marcus.lin**
Just drop `generated_at`? Then the whole file is stable and you hash the whole file. Done.

**09:39 ingrid.solberg**
Can't drop it. The auditors require provenance metadata on the evidence document — when it was generated, on what host, over what directory. A snapshot with no generation time is not admissible to them, they'll reject it as an undated record. So the volatile fields have to *exist* in the file. They just can't be in the thing we cite.

**09:40 ola.ferrand**
Then the answer writes itself. The hash covers the *evidence* — the canonical badge list and the counts — and the provenance metadata sits in the file alongside the digest but outside the digested region. The document says, in effect, "here is the evidence, here is its hash, and here — separately — is when and where I wrote this down." Two runs over the same badges produce the same evidence-hash even though `generated_at` differs, which is exactly the property Ingrid needs. The metadata is context, not evidence.

**09:41 kenji.watanabe**
I like that but be careful how you word it, because "the hash covers the badge list and counts but not the metadata" is a rule someone will implement three ways. Whatever region is hashed has to be a *precisely defined* canonical serialization, not "the badges bit, you know, roughly". If the digested region is itself ambiguous we've moved the nondeterminism inward instead of killing it.

**09:42 dana.whitfield**
Agreed, and that's the discipline: the digested region is a canonical document in its own right — sorted keys, sorted badges, minimal whitespace, UTF-8, the whole list applied to *that region specifically* — and the outer file wraps it with provenance. The digest is over the canonical bytes of the evidence, published in the file so the file is self-describing: you can recompute the digest from the evidence region and check it matches. That also means the auditor doesn't have to trust our metadata to trust our evidence.

**09:43 priya.raghunathan**
So the citation the auditors put in their report is the evidence-digest, not the whole-file hash. Ingrid, does that hold up on their side? Because it changes what they record.

**09:45 ingrid.solberg**
It holds up and honestly it's *better* for them. Today they hash the file and get a number that changes every run, which is why we're here. If we give them a digest that covers exactly the evidence and is stable across runs and machines, that's a far stronger citation — two independent runs on two hosts producing the same evidence-digest is corroboration, not a finding. I'll take it to their lead on the 11:00. I think they'll be relieved.

**09:46 kenji.watanabe**
One more on the counts, since they're inside the digested region. Right now the diff shows `counts:{trusted:41,rejected:2,unverifiable:1}`. What happens on a directory where nothing was rejected? Does `rejected` disappear from the object, or does it stay as `rejected: 0`?

**09:47 marcus.lin**
Drop it. If there's nothing rejected, why carry a zero. Smaller file, less noise.

**09:48 ingrid.solberg**
No — and this isn't a preference, it's a hard requirement from their side and I've been burned by it. The auditors validate every snapshot against a JSON Schema before they'll ingest it, and their schema marks the count keys as required. An *absent* key fails validation outright — `provctl validate` rejects the whole document, it doesn't just warn. So a missing `rejected` key isn't "cleaner", it's a rejected evidence submission. A zero is a fact: "we looked, and zero were rejected." An absent key is ambiguous: "did zero get rejected, or did this worker not even know how to count rejections?" For an auditor those are completely different and the second is a red flag.

**09:49 dana.whitfield**
Which is the general principle and I want it written down as its own line, because it'll come up again: a missing key is *worse* than a zero. Absence is ambiguous, zero is a measurement. Every status the worker can produce gets a count key, always present, even when the value is zero. The set of count keys is fixed and does not depend on what happened to be in the directory. That's what makes two snapshots comparable — they have the same shape whether or not the same things happened.

**09:50 kenji.watanabe**
Good. And that also means the digested region has a *fixed shape*, which helps determinism — the object always has the same members in the same sorted order, only the values move. That's much easier to canonicalise than a document whose keys appear and vanish.

**09:51 marcus.lin**
Alright, I withdraw "drop the zeros" too. I'm 0 for 2 today. Zeros stay, present always.

**09:52 priya.raghunathan**
That's the spec then, and it's tighter than I expected before coffee. Let me not summarise it into a table because Dana will glare at me, but the shape of it: canonical minified JSON, byte-sorted keys, badge list sorted by an intrinsic total key, UTF-8 no BOM, consistent escaping, all counts always present including zeros, digest over the canonical evidence region, provenance metadata in the file but outside the digest. Anyone object before Ingrid takes it to the auditors?

**09:54 tomas.berg**
I've been lurking and I have exactly one objection and it's about the *filenames*, which nobody's mentioned and which is going to bite us the same way the field order did. Look at Ingrid's two files again: `snapshot.audit-host.2026-05-24.json` versus `snapshot.laptop.2026-05-25.json`. The audit host stamped the badge date, my — sorry, her laptop stamped today's date. But worse, look at the `generated_at` values inside: `2026-05-24T23:14:07Z` on the audit host and `2026-05-25T07:41:52+02:00` on the laptop. One's UTC, one's local with an offset.

**09:55 tomas.berg**
Those two instants are 8 hours apart on the clock but they're the same night's work. If we ever put a local-time stamp — with or without offset — into a filename, we get two files for the same run that sort differently and confuse every human trying to find "last night's snapshot." I've watched this exact movie with release tarballs. Everything that is a time, in a filename or in the provenance metadata, is UTC with a `Z`. No local time. No offsets. Ever.

**09:56 ola.ferrand**
Strong agree and it's the same disease as the locale sorting — it's canonical on the machine that wrote it and ambiguous everywhere else. `+02:00` means nothing to the auditor in a different zone without doing the math, and it means nothing to a future reader after we've all forgotten it was CEST that week. Normalise to UTC at the point of writing. The offset is not information anyone downstream benefits from.

**09:57 kenji.watanabe**
And it's not just cosmetic for the metadata field either. If `generated_at` were ever inside the digested region, a local-vs-UTC representation of the *same instant* would produce two different digests. It's outside the region so we dodge that here, but the rule "times are always UTC Z, one representation" needs to hold everywhere or it'll find a way back into a hashed region eventually.

**09:58 tomas.berg**
Exactly my fear. Pin it once, everywhere: UTC, `Z` suffix, one format. Filenames and metadata both. I'll open REL-4830 to fix the snapshot filename convention on the audit host's nightly, because right now it's stamping local date and that's how we ended up with `.2026-05-24.` and `.2026-05-25.` for one directory.

**09:59 ingrid.solberg**
Please do, and link it to SEC-4821 so the auditors can see the filename thing is tracked separately from the byte thing. They noticed the filename mismatch too and asked whether it was significant. I want to be able to say "no, tracked in REL-4830, purely a naming convention, doesn't affect the evidence digest."

**10:02 ola.ferrand**
Before this thread wraps I want to flag something that isn't the snapshot at all, so nobody thinks it's solved just because the snapshot is. The exact same canonicalisation problem bites us a second time, in a completely different place, and it's more dangerous there.

**10:03 ola.ferrand**
Think about what the worker does *before* it ever writes a snapshot. To decide a badge's status it has to check the signature, and a signature is computed over some bytes. Whoever produced the badge serialised the statement to bytes and signed those bytes. When we verify, we have to reconstruct the exact same bytes to check the signature against. That reconstruction is a canonicalisation problem — the identical one we just spent an hour on for the snapshot. Same JSON, same "which key order, which whitespace, which encoding" questions.

**10:04 kenji.watanabe**
So if the signer and the verifier canonicalise the statement even slightly differently...

**10:04 ola.ferrand**
Then verification is a coin flip. Not "usually works" — *a coin flip that depends on how the JSON happened to be written that day*. Re-order two keys, add a space after a colon, escape a slash differently, and the bytes the verifier hashes are not the bytes that were signed, and a perfectly legitimate badge fails. Or, just as bad in the other direction, sloppiness that lets two different byte-strings both "pass" is its own hole. The signature is only meaningful over a preimage that both sides agree on, exactly, byte-for-byte.

**10:05 dana.whitfield**
This is a real and separate concern and I don't want it turning into a debugging tangent in *this* thread, which is a controls response about snapshot bytes and nearly ready to send. Let me state Ola's point at the level it belongs: canonicalisation is not a snapshot feature, it's a property the *whole system* needs anywhere bytes are hashed or signed, and the signature preimage is the highest-stakes place it appears. I'm deliberately not going to sketch how the preimage is built here — that's a design conversation with its own thread and its own review, and writing a recipe into a war-room scroll is how you get three incompatible implementations of it. The observation stands: same disease, second location, and that location decides whether we trust a release at all.

**10:06 ola.ferrand**
That's all I wanted — the observation on the record, not the algorithm. I'll raise the preimage discussion properly somewhere it can be reviewed. I just refuse to let us fix the snapshot, feel clever, and forget the harder version of the same problem is sitting one layer down.

**10:07 priya.raghunathan**
Noted and filed as "separate, out of scope for SEC-4821, do not solve it in this thread." Ola open whatever ticket you need for the preimage design, but not here. Ingrid, are you good for the 11:00?

**10:08 ingrid.solberg**
Nearly. One practical thing I need before the call: a real hash. I want to paste an actual evidence-digest into SEC-4821 as the worked example, so when the auditors ask "what does a citation look like" I show them one instead of describing it. Can someone produce a canonical snapshot over `/app/var/badges/2026-05-24/` — even a hand-rolled canonical one for now — and give me the digest over the evidence region.

**10:10 ola.ferrand**
I canonicalised the four-badge example by hand to the spec we just agreed — byte-sorted keys, badges sorted by artifact digest, minified, UTF-8, counts all present. Over the evidence region only, not the provenance:

```
sha256(evidence) = 3e7b1c9f4a2d8e05b6f1c07a9d3e5f21b8c4a6d0e2f7913b5c8a0d4e6f9b2c1a
```

Ran it twice on two different boxes to be sure it's not just stable in my head. Same digest both times. That's the number, Ingrid — but flag clearly in the ticket that it's a hand-canonicalised reference value, not yet the worker's own output, because the writer doesn't emit canonical bytes today.

**10:11 ingrid.solberg**
Perfect, that's exactly what I needed. Pasting into SEC-4821 now with that caveat spelled out:

> Reference evidence-digest for `/app/var/badges/2026-05-24/` (44 badges) under proposed canonical form: `sha256:3e7b1c9f4a2d8e05b6f1c07a9d3e5f21b8c4a6d0e2f7913b5c8a0d4e6f9b2c1a`. NOTE: hand-canonicalised reference value pending worker emitting canonical output natively; provenance metadata excluded from digest region. Filename convention tracked separately in REL-4830.

**10:12 ingrid.solberg**
And this is why the "counts always present" rule earns its keep already — I re-ran `provctl validate` against the auditors' schema on Ola's canonical example and it passes, because all three count keys are there. My laptop snapshot earlier *also* passed, but only because that directory happened to have a rejection in it. A directory with zero rejections and the old drop-the-zero behaviour would have failed validation and I'd never have known until an auditor tried to ingest it. So that requirement isn't theoretical, it's the difference between a submittable document and a rejected one.

**10:13 kenji.watanabe**
That's a good stress case to keep. Can we get a badge directory in the fixtures where one status count is genuinely zero, so whatever the worker eventually emits is tested against exactly that "absent key would fail" scenario? The bug we care about only shows up when a count is zero, which is precisely when a naive writer omits the key.

**10:14 ola.ferrand**
Yes. I'll add a fixture directory that's all-trusted — zero rejected, zero unverifiable — so the canonical output has to carry `"rejected":0,"unverifiable":0` and validation has to pass on it. If a future change ever starts dropping zero counts, that fixture goes red immediately instead of six months later in an audit.

**10:16 yusuf.adeyemi**
late follow-up, not reopening the format war i swear. for search-api's dashboards we consume these snapshots too, and we sort the badge list ourselves on ingest anyway. so a canonical on-disk order doesn't hurt us — if anything our dashboard stops flickering when the underlying order shuffles between runs. just confirming it doesn't break any consumer i know of. it doesn't.

**10:18 marcus.lin**
payments reads them but only through a script that parses the JSON and pulls its own service out, order-independent. Canonical is fine for us. My only ask stands — a `jq` one-liner in the runbook so nobody at 2am tries to read the raw file and rage-quits. I'll add it to the on-call notes myself.

**10:19 tomas.berg**
Release tooling doesn't consume them, only produces the badges that get scanned. No breakage from my side. REL-4830 is open for the filename/UTC convention, linked to SEC-4821.

**10:20 dana.whitfield**
Then I think the controls response is coherent. The one thing I want Ingrid to *not* claim to the auditors is that it's shipped — the spec is agreed, the reference digest is hand-rolled, the worker doesn't emit canonical bytes yet. If she says "reproducible today" and they diff two real worker outputs on the call it'll still drift and we'll have burned trust. Say "agreed canonical form, reference digest attached, worker conformance in flight." Under-promise.

**10:21 ingrid.solberg**
That's exactly how I'll frame it. "Here is the canonical form we've agreed, here is a worked reference digest that's stable across two hosts, here is the schema-validation behaviour including the zero-count case, and here are the two tickets — SEC-4821 for the byte reproducibility, REL-4830 for the filename convention — tracking the work to make the worker emit this natively." Honest about state, concrete about direction. That's a call I can win.

**10:22 priya.raghunathan**
Then go win it. Ola, the preimage observation is yours to carry out of here into its own thread — not this one. Everyone else, the snapshot spec is what's in this scroll, argue with it there and not in a DM I'll never find. I'm marking the war-room item as spec-agreed, implementation-tracked. Thanks all.

**10:24 kenji.watanabe**
One tiny correction before it's archived, because someone will grep this later and take it literally: if anyone half-remembers this thread as "sort the badges alphabetically", it's not. Byte order of the sort key, badges by intrinsic digest, no alphabet, no locale. Didn't want the wrong word cached in someone's memory.

**10:25 ola.ferrand**
Appreciated. The number of outages that started as "someone half-remembered a spec from a chat" is not small. Byte order, everywhere, full stop.

**10:26 ingrid.solberg**
Thank you all, genuinely. Going into the call. If it goes sideways I'll be back in here within the hour, but I don't think it will — a stable digest they can cite is exactly the thing they came to ask for, we just have to hand it to them the right shape.
