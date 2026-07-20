# Terminus 2nd Edition — Frequently Asked Questions

*Last updated: June 29, 2026*

> **How to use this document:** Sections are ordered to follow the task lifecycle — from onboarding through building, testing, submitting, and getting paid. Use `Ctrl+F` to search for keywords, or jump to a section below.

#### Quick Navigation
1. [Getting Started & Onboarding](#1-getting-started--onboarding)
2. [CLI Setup & API Keys](#2-cli-setup--api-keys)
3. [Task Structure: Milestones & File Layout](#3-task-structure-milestones--file-layout)
4. [Difficulty, Language & Codebase Size](#4-difficulty-language--codebase-size)
5. [Testing & Docker Troubleshooting](#5-testing--docker-troubleshooting)
6. [Submissions & Reviews](#6-submissions--reviews)
7. [Rubrics & Quality Checks](#7-rubrics--quality-checks)
8. [Compensation & Payment](#8-compensation--payment)
9. [Project Scope & Support](#9-project-scope--support)
10. [Known Issues & Workarounds](#10-known-issues--workarounds)

---

## 1. Getting Started & Onboarding

**How do I get started on this project?**
Review the [project website](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal), then check pinned posts in #terminus-2nd-edition-submission and #terminus-2nd-edition-announcements. Once you've reviewed the materials, complete the **Terminus-2nd-Edition-Assessment** on your [Snorkel dashboard](https://experts.snorkel-ai.com/home) under "My Projects." You must score 80% or higher to advance and will receive your results with next steps via Slack DM once ready.

**Where do I find the assessment?**
On your [dashboard](https://experts.snorkel-ai.com/home), look for **Terminus-2nd-Edition-Assessment** under "My Projects" (you may need to scroll or search). Click the Submissions node to begin. If you don't see it, ask in #terminus-2nd-edition-submission.

**How soon do I need to take the assessment? Are there deadlines?**
No deadlines — take it whenever you're ready. However, the assessment has a **90-minute time limit** once started, so review the materials first.

**I passed the assessment — what happens next?**
A team member will contact you with results, typically the next business day (excluding weekends). You'll receive $25 for completing the assessment, plus an additional $25 bonus for scoring 80%+.

**Are there training videos?**
Yes — three videos by fellow Terminus Expert Brady Nguyen: *Understanding Terminus*, *Understanding Submissions*, and *Understanding Revisions*. Available on the [onboarding page](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal/docs/onboarding/platform-onboarding).

**Where is the task gallery? I logged in but don't see any tasks.**
The **task gallery** and the **submission portal** are separate sites. The gallery (browse/choose tasks) is on the [documentation site](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/). The portal (upload completed work) is on the [Snorkel Experts platform](https://experts.snorkel-ai.com/home). Build locally from the gallery, then submit through the portal.

**Should I wait for my first task to be reviewed before starting another?**
No — work on and submit multiple tasks in parallel.

**How do I initialize a new task with the CLI?**
`stb init my-task-name -p "terminus-2nd-edition" -t default`

---

## 2. CLI Setup & API Keys

**I'm getting "Your account is not assigned to any Terminal-Bench project."**
Expected if you haven't been onboarded to the main project yet. Complete and pass the assessment first, then wait for team confirmation. CLI and API keys only work after assignment.

**I hit the maximum key refresh limit (10).**
Post in #terminus-2nd-edition-submission and ask an admin to reset your key. They can delete the old key so you can regenerate, or top it up manually. You don't need to run the refresh command after an admin resets it.

**`stb login` works but `stb keys refresh` fails with "Authentication failed."**
Known intermittent issue. Try: (1) regenerate a new API key in the browser using the "Copy" button, (2) run `stb login` again, then (3) retry `stb keys refresh`. If it persists, post in Slack and tag the team.

**How do I get an API key for agent testing?**
You don't need your own. The project provides AI credentials through the CLI — follow the [CLI User Guide](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal/docs/cli-user-guide) and run `stb keys refresh`.

**My API key is exhausted or giving errors mid-work.**
Keys have a usage budget. Run `stb keys refresh` for a new one. There's a cap on how many times you can refresh; once you hit it, ask an admin to reset or raise it. Keys can also become temporarily rate-limited — wait a few minutes and retry. Running concurrent agent tests exhausts keys faster.

**I'm having trouble upgrading `stb`.**
Follow the upgrade command in the [CLI User Guide](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal/docs/cli-user-guide). A 403 Forbidden error usually means the download link was temporarily rotated — try again later. Always verify your version with `stb --version` before troubleshooting other issues.

---

## 3. Task Structure: Milestones & File Layout

> ⚠️ *This is the most common source of revision requests. Read carefully.*

> **Terminology note:** The Harbor framework refers to milestones as **multi-step tasks** ([Harbor docs](https://www.harborframework.com/docs/tasks/multi-step)). We use "milestones" throughout our docs; the two are interchangeable.

**What files does a milestone task require?**

For a task with N milestones, your zip should contain:

| File(s) | What goes in it |
|---|---|
| `task.toml` | Includes one `[[steps]]` block per milestone with `name = "milestone_N"`, `[steps.agent].timeout_sec`, and `[steps.verifier].timeout_sec`. `number_of_milestones` in `[metadata]` must equal the number of `[[steps]]` blocks. |
| `environment/Dockerfile` | Standard Dockerfile (or `docker-compose.yaml`) — one shared environment for all milestones |
| `steps/milestone_1/instruction.md` … `steps/milestone_N/instruction.md` | Per-milestone prompt. Milestone 1's `instruction.md` should include the overall task context the agent needs to get oriented; subsequent milestones can be shorter |
| `steps/milestone_1/tests/test_m1.py` … `steps/milestone_N/tests/test_mN.py` | One pytest file per milestone (with a `TestMilestoneN` class) that scores only that milestone's completion |
| `steps/milestone_1/tests/test.sh` … `steps/milestone_N/tests/test.sh` | Per-milestone test runner that produces `/logs/verifier/reward.txt` |
| `steps/milestone_1/solution/solveN.sh` (one per milestone) | Each milestone's oracle solution, independently scoped to that milestone only |
| `steps/milestone_1/solution/solve.sh` (one per milestone) | Thin wrapper that runs the milestone's `solveN.sh` |
| Rubrics (via UI) | One per milestone; each needs ≥1 negative criterion, valued 10–40 pts |

There must be **no** root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md` files in a milestone task. See the [Milestones page](/portal/docs/understanding-tasks/milestones) for the full layout and a copy-pasteable `task.toml` example.

**Where do per-milestone instructions live?**
In `steps/milestone_N/instruction.md`. The agent sees only the current milestone's instruction when working on it. Milestone 1's instruction should include any overall task context; later milestones can be shorter and describe only the new requirements.

**I'm getting errors about missing `milestone_x.md` or `solveN.sh` at the root.**
The old flat layout (root-level `milestone_x.md`, `solution/solve1.sh`, `tests/test_m1.py`) has been replaced by the per-milestone `steps/` directory layout. If you're seeing checks complaining about the old files, you're likely on an outdated template — re-download the milestone skeleton from the [Task Requirements](/portal/docs/understanding-tasks/task-requirements) page.

**What should `number_of_milestones` be for a task without milestones?**
`0`. Setting it to `1` for a non-milestone task is incorrect.

**Do new file structure requirements apply to my older submissions that came back for revision?**
No — new guidelines apply to new submissions only. If automated checks block a revision with new-only rules, report it in Slack. Workaround: make a trivial change (add a space, capitalize a letter) and resubmit to force a fresh check instead of cached results.

---

## 4. Difficulty, Language & Codebase Size

### Difficulty

**What are the difficulty requirements?**
- **Python tasks**: Must be **HARD**.
- **Non-Python tasks** (Go, Java, TypeScript, etc.): **MEDIUM** or **HARD**.
- **TRIVIAL** means the agent pass rate is too high — make the task harder.

**What qualifies as HARD?**
A task is HARD when accuracy is **≤ 20%** on either the **best** model OR the **worst** model (across GPT-5.5 and Claude Opus 4.8). See [Difficulty Guidelines](/portal/docs/understanding-tasks/difficulty-guidelines) for the full breakdown of Easy / Medium / Hard thresholds.

**My task keeps coming back as TRIVIAL. What types of tasks pass as HARD?**
Complex multi-step debugging, nuanced edge cases, larger codebases, and workflows requiring discovery across multiple files. Single-bug or template-based tasks tend to be flagged as too easy.

**My non-Python task (e.g., Go) is being flagged as "Python requires HARD."**
All verifier tests are written in Python pytest, but Python test infrastructure alone should not be listed in `task.toml` `languages`. The `languages` field should describe the main task/oracle/agent work. Remove Python from `languages` if it is present only because of `tests/test_outputs.py`.

### Codebase Size

**What is `codebase_size` and how is it determined?**
Based on file count in `environment/` (excluding Dockerfile and docker-compose). It describes the starting environment, not what the agent generates:

| Value | File count | Notes |
|---|---|---|
| `minimal` | 0–19 | Allowed |
| `small` | 20+ | |
| `large` | 200+ | |

Values are **case-sensitive** in `task.toml` — use `"small"`, not `"Small"`.

**How do I get to 20+ files for a "small" codebase?**
Use files from public open-source repos to build a realistic project environment. Files don't all need to be touched by the task, but they shouldn't be blank filler — they should make the project feel real. The team is also working on sourcing repos to simplify this.

### Timeouts & Concurrency

**What is the agent timeout limit?**
**1800 seconds** (30 minutes). Agents failing due to timeout contribute to difficulty.

**Can I run concurrent agent tests (GPT-5.5 and Opus at the same time)?**
Yes, but expect API errors and faster key exhaustion. Refresh keys more frequently if you do.

---

## 5. Testing & Docker Troubleshooting

<div id="solvable-vs-passing-a-run"></div>

### Solvable vs. passing a run

**What’s the difference between a task being “solvable” and the agent “passing a run”?**

- **Passing a run** means a single agent run where **all** unit tests pass.
- **Solvable** (for the benchmark / CI) means that **across 10 agent runs**, **each** individual unit test passes **at least once** (not necessarily in the same run). A task can have **no** run where every test passes and still be solvable—the model may only satisfy different parts of the task on different runs. **Unsolvable** means at least one test never passes in any of those 10 runs.

To replicate this locally with `-k 10`:

```bash
stb harbor run -m @openai/gpt-5.5 -p ./task -k 10
stb harbor run -m @anthropic/claude-opus-4-8 -p ./task -k 10
```

**What are the correct model strings?**
| Model | String | Common mistakes |
|---|---|---|
| GPT | `@openai/gpt-5.5` | `gpt-5-5`, `@openai-tbench/gpt-5-5` |
| Claude Opus | `@anthropic/claude-opus-4-8` | `claude-opus-4.8` (dot instead of hyphen) |

If you see `INVALID_MODEL_NOT_ALLOWED`, double-check your model string.

**502 Bad Gateway or RateLimitError with Opus 4.8, but GPT-5.5 works fine.**
Regenerate a fresh API key. If it persists, run with `--debug` and share the output in Slack.

### Common Build & Test Failures

**Do tests have to be written in Python?**
Yes. All verifier assertions must be Python pytest tests (`tests/test_outputs.py` for non-milestone tasks, or `test_mN.py` for milestone tasks). `tests/test.sh` is a bash wrapper that runs pytest and writes the reward file; it should not invoke Java, JavaScript, Go, or other language-specific test frameworks directly. For non-Python tasks, use Python pytest tests to call the relevant command, service, or output files.

**My task passes locally but fails on the platform — `reward.txt` not found.**
Almost always one of three causes:

**Cause 1: Entrypoint blocks execution.**
If `entrypoint.sh` ends with a blocking command like `exec nginx -g 'daemon off;'`, it prevents `test.sh` from running. Fix:
```bash
nginx
exec "$@"
```

**Cause 2: `set -euo pipefail` causes early exit.**
If any command fails before writing `reward.txt`, the script exits. Drop `-e` and capture the exit code. Pytest and any plugins should be pre-installed in the Docker image; `test.sh` should only run the verifier and write the reward file (see [Writing Tests](/portal/docs/creating-tasks/writing-tests)):
```bash
set -uo pipefail
mkdir -p /logs/verifier

python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m1.py -rA && rc=0 || rc=$?

if [ $rc -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

**Cause 3: Missing output directory.**
Add `mkdir -p /logs/verifier` near the top of `test.sh`. The starter template may not include this line — add it yourself.

**The quality check flags `source "$HOME/.local/bin/env"` as a typo.**
Known false positive — ignore it.

**All my agent runs fail with no verifier output — `verifier_did_not_run` across every run, even on a simple task.**
The most common cause is missing `tmux` and/or `asciinema` in your Dockerfile. The agent runtime requires both to start a session — without them, agents cannot run at all regardless of task quality. Add them to your `environment/Dockerfile`:
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*
```

**The LLMaJ review says "NOT_APPLICABLE" with an empty summary.**
Agents couldn't start (often a tmux session failure — see above). Report the task UUID in Slack.

**`stb harbor check` fails with "Claude Code returned an unexpected response" or a Usage Policy error.**
This is a **provider content refusal**, not a CLI bug and not a verdict on your task's correctness. The model running the quality check (e.g., Claude Code / GPT-5.5) flagged something in your task content as potentially violating the [Usage Policy](https://www.anthropic.com/legal/aup). The surface error is misleading — you may see `Received result: "success", but the operation was treated as a failure`, while the underlying cause is `API Error: Claude Code is unable to respond to this request, which appears to violate our Usage Policy. Try rephrasing the request in a new session or change your model.` Work through these in order:
1. **Re-run the check** — refusals can be intermittent; a fresh session sometimes passes.
2. **Switch the judge model** — re-run with the other model (swap `@openai/gpt-5.5` ↔ `@anthropic/claude-opus-4-8`). A refusal on one model frequently clears on the other.
3. **Review your task content** — security/exploit/malware-adjacent framing, harmful instructions, or sensitive-looking data can trip the flag even for legitimate tasks. Where possible, frame the task in clearly legitimate, defensive/educational terms.
4. **Escalate** — if the task is legitimately security-related (e.g., a CTF or defensive-security task) and keeps refusing on every model, post the task UUID in #terminus-2nd-edition-submission so the team can review.

### Docker Issues

**My `environment/app` folder isn't being mounted in Harbor.**
Harbor sets the build context to `environment/`. If your Dockerfile references files outside that directory, Docker won't find them. Move everything your Dockerfile needs into `environment/`.

**Docker network errors after running many tests.**
Run `docker network prune` to clean up stale networks.

**My Dockerfile references a base image that seems unavailable.**
Some images may not be accessible on the platform. Post the exact image name and task UUID in Slack.

---

## 6. Submissions & Reviews

### Submitting

**How do I check the status of my tasks? How do I see what state my submissions are in?**
Use the CLI: `stb submissions list -p PROJECT_ID` returns every submission you've made for a project along with its current state. Add `--show-folder-names` to also see the local task folder name each submission came from (slower).

You can also drill into a specific submission:
- `stb submissions view SUBMISSION_ID` — open the submission in the browser
- `stb submissions feedback SUBMISSION_ID` — download the latest reviewer/automated feedback
- `stb submissions download SUBMISSION_ID` — download the submitted task files

**Submission status reference:**

| Status | Meaning | Can update? |
|---|---|---|
| `EVALUATION_PENDING` | Automated checks running | No |
| `NEEDS_REVISION` | Reviewer requested changes — update with `stb submissions update` | Yes |
| `REVIEW_PENDING` | Waiting for a human reviewer | No |
| `ACCEPTED` | Task accepted | No |
| `OFFERED` | Offer made | No |
| `REJECTED` | Task rejected | No |
| `SKIPPED` | Task skipped | No |

See the [CLI User Guide → Check submission status](/portal/docs/cli-user-guide#check-submission-status) for the full set of submission commands.

**What is the daily submission limit?**
Net-new tasks are capped per day by Expert level:

| Expert level | Net-new tasks per day |
|---|---|
| New (before 2 accepted tasks) | 2 per day |
| Veteran (2+ accepted tasks) | 3 per day |

Only **net-new** submissions count toward this cap — **revisions do not**. Resets at **midnight UTC** (~7–8 PM EST).

**What is the revision-queue limit?**
You can have at most **10 submissions in your revision queue at once**. Once you reach 10, you're blocked from submitting any net-new tasks until you make room. To clear a task you don't intend to revise, hit **"Discard"** on it — that rejects the task and removes it from your revision queue.

If you're blocked from a net-new submission while under your daily limit, check whether your revision queue is full (10) before reporting a bug.

**My submission is auto-rejected by AutoEval even though it passes manual checks.**
Known intermittent issue. Resubmit. If persistent, post your submission ID and failing build ID in Slack.

**All my quality checks pass and say "READY TO USE," but a reviewer still sent it back.**
"READY TO USE" is the *automated* agent review — it's not a guarantee of human approval. Reviewers evaluate rubric quality, instruction clarity, test coverage, and task design beyond what automated tools can assess.

### Reviews & Disputes

**How long does review take?**
Assessments: ~24 hours (excluding weekends). Task reviews: 1–7 business days.

**My task keeps coming back with blank, incorrect, or mismatched feedback.**
Known caching issue — reviewers may receive stale or wrong zip files. If the feedback references files, code, or features not in your submission, dispute with screenshots and escalate in #terminus-2nd-edition-submission.

**I disagree with the reviewer. What should I do?**
Use the dispute mechanism on the portal. Reference specific docs or announcements. If the reviewer keeps returning the same incorrect feedback, escalate in Slack by tagging the team.

**Are new guidelines being applied to my old revisions?**
They shouldn't be — new rules are for new submissions only. If a reviewer enforces new requirements on an older task, flag it. Noelle has confirmed reviewers are aware of this distinction.

---

## 7. Rubrics & Quality Checks

**What are the rubric requirements?**

| Requirement | Severity |
|---|---|
| ≥1 negative criterion per milestone rubric | **Hard requirement** — triggers revision if missing |
| 10–40 points per milestone (max cumulative score) | **Flaggable**, but not a sole reason for revision |

**How do I generate rubrics?**
Check "Generate Rubric(s)" and submit _without_ checking "Send to Reviewer". Generation happens during CI checks (not Fast Static Checks) — rubrics don't appear instantly. Editing is only possible through the portal UI.

**My rubrics disappear or appear empty after a revision cycle.**
Known platform bug. Report with the task UUID in Slack.

---

## 8. Compensation & Payment

**What's the pay per task?**
See the [Rate Schedule](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal/docs/reference/rate-schedule). Base rate + bonuses for codebase size, milestones, and non-Python/non-Bash languages.

**When do I get paid?**
Payouts follow a **Friday-to-Thursday** cycle — tasks accepted in that window are paid the following Friday. Example: accepted Monday the 7th → paid around Friday the 17th.

**Do I get paid for tasks still in review?**
No. Payout happens only if your submission reaches the state of '**Accepted**'

**Can I get paid for tasks from Terminus 1st Edition?**
No. That project was deprecated December 2025. Non-accepted tasks from it will not be paid.

---

## 9. Project Scope & Support

**How long will this project last?**
At least another month from mid-April 2026, with possible extension based on quality and delivery velocity.

**Are there deadlines?**
No — work at your own pace.

**Will more tasks be added to the gallery?**
Periodically, yes. If it looks sparse, check back or ask in Slack.

**Are there office hours?**
Yes. The current schedule is **pinned at the top of the `#terminus-2nd-edition-announcements` Slack channel under the "Office Hours" section** — that's where you'll find the latest dates, times, and Zoom links. Sessions are held multiple times per week (typically each weekday). See the [Office Hours page](/portal/docs/reference/office-hours) for more details.

**Where should I ask questions?**

| Channel | Use for |
|---|---|
| #terminus-2nd-edition-submission | General questions, tech issues, submission help |
| #terminus-2nd-edition-announcements | Guideline updates (read-only for most) |

---

## 10. Known Issues & Workarounds

*As of April 16, 2026.*

### Platform & Submission

| Issue | Workaround |
|---|---|
| AutoEval failing intermittently on "Send to reviewer" | Resubmit; report with IDs if persistent |
| Rubrics disappearing during revision cycles | Report with task UUID |
| `EVALUATION_PENDING` status stuck on tasks | Report task UUID in Slack |

### Reviews & Feedback

| Issue | Workaround |
|---|---|
| Reviewer feedback references wrong task/files | Dispute with screenshots; escalate in Slack |
| New guidelines enforced on older revisions | Make trivial change and resubmit to bypass cached checks. If still blocked, report in Slack |
| Rubric evaluator failing to parse `# Rubric N` headers | Review quality manually; fix in progress |

### CLI & Testing

| Issue | Workaround |
|---|---|
| `stb keys refresh` limit reached | Ask admin in Slack to reset or raise it |
| Non-Python tasks flagged as Python | Remove Python from `languages` in `task.toml` |
| Quality check false-flags `source "$HOME/.local/bin/env"` | Ignore this specific flag |
| Agent logs unavailable for some reviews | Report with task UUID |
| Docker network limit from repeated harbor runs | Run `docker network prune` |
| `stb harbor check` fails: "unexpected response" / Usage Policy refusal | Provider content refusal — re-run, switch judge model (`gpt-5.5` ↔ `claude-opus-4-8`), review content; escalate with UUID if a legitimate task keeps failing |
