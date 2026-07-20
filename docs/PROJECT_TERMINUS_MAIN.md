# Project Terminus — Complete Contributor Guide

> Snorkel AI's expert task-creation program for Terminal-Bench 2.0
> Last updated: June 2026

---

## Table of Contents

1. [What Is Project Terminus?](#1-what-is-project-terminus)
2. [Essential Links & Resources](#2-essential-links--resources)
3. [Your Role as an Expert](#3-your-role-as-an-expert)
4. [Task File Structure](#4-task-file-structure)
5. [File-by-File Breakdown](#5-file-by-file-breakdown)
6. [Task Requirements](#6-task-requirements)
7. [Difficulty Ratings](#7-difficulty-ratings)
8. [Task Categories & Subcategories](#8-task-categories--subcategories)
9. [Milestones](#9-milestones)
10. [The Rubric](#10-the-rubric)
11. [Diversity Rules](#11-diversity-rules)
12. [Choosing the Right Task Skeleton](#12-choosing-the-right-task-skeleton)
13. [Step-by-Step Submission Workflow](#13-step-by-step-submission-workflow)
14. [Quality Checks Explained](#14-quality-checks-explained)
15. [Peer Review Process](#15-peer-review-process)
16. [Compensation & Office Hours](#16-compensation--office-hours)
17. [Quick Reference Checklists](#17-quick-reference-checklists)

---

## 1. What Is Project Terminus?

Project Terminus is Snorkel AI's program to build a high-quality dataset of complex terminal tasks for AI agent evaluation — modeled after **Terminal-Bench**, an open-source benchmark co-authored by Snorkel AI, Stanford University, and the Laude Institute.

Terminal-Bench evaluates how well AI agents (like GPT and Claude Opus) complete real-world, multi-step tasks inside a Linux terminal environment — things like compiling code, training ML models, configuring servers, scraping data, and more.

**Your job:** Create these tasks, along with a working solution and tests that verify whether an AI agent completed them correctly.

---

## 2. Essential Links & Resources

| Resource                        | URL                                                                                     |
|---------------------------------|-----------------------------------------------------------------------------------------|
| Terminal-Bench main site        | https://www.tbench.ai                                                                   |
| Task structure documentation    | https://www.tbench.ai/docs/task-overview                                                |
| Task creation quickstart        | https://www.tbench.ai/docs/task-quickstart                                              |
| Task ideas / inspiration        | https://www.tbench.ai/docs/task-ideas                                                   |
| Contributing guide              | https://www.tbench.ai/docs/contributing                                                 |
| Setup guide                     | https://www.tbench.ai/docs/setup-guide                                                  |
| Leaderboard                     | https://www.tbench.ai/leaderboard/terminal-bench/2.0                                   |
| All benchmarks                  | https://www.tbench.ai/benchmarks                                                        |
| GitHub repo (Laude Institute)   | https://github.com/laude-institute/terminal-bench                                       |
| Harbor framework (runner)       | https://harborframework.com                                                             |
| Harbor docs (running TB)        | https://harborframework.com/docs/running-tbench                                         |
| Discord community               | https://discord.gg/2Pe5uWGcV3                                                           |
| Snorkel AI                      | https://snorkel.ai                                                                      |
| Snorkel blog — TB 2.0 launch    | https://snorkel.ai/blog/terminal-bench-2-0-raising-the-bar-for-ai-agent-evaluation/    |
| Snorkel blog — TB explainer     | https://snorkel.ai/blog/evaluating-coding-agent-capabilities-with-terminal-bench-snorkels-role-in-building-the-next-generation-benchmark/ |
| Research paper (arXiv)          | https://arxiv.org/pdf/2602.21193                                                        |
| Snorkel GitHub                  | https://github.com/snorkel-ai                                                           |
| Snorkel Expert Platform         | (provided via your onboarding email / Slack)                                            |
| Task Skeletons                  | (available in Slack resources tab and project website)                                  |
| Slack — Submission channel      | (provided via your onboarding email)                                                    |
| Slack — Announcements channel   | (provided via your onboarding email)                                                    |

---

## 3. Your Role as an Expert

As a Project Terminus expert, you create **task packages** — zip files that contain everything needed to challenge an AI agent and verify its performance.

Each task package contains:

- A **prompt** (natural language instructions for the agent)
- A **Docker environment** the agent works inside
- An **Oracle solution** proving the task is solvable
- **Tests** that verify whether the agent actually succeeded
- A **rubric** that grades the quality of the agent's approach

Tasks are tested against state-of-the-art models (GPT5.5 and Claude Opus4.8). We want tasks where the agent does NOT always succeed — that's the whole point. We're mapping the weak spots of these models.

---

## 4. Task File Structure

```
your_task_name/
├── instruction.md          ← Prompt given to the AI agent
├── task.toml               ← Metadata about your task
├── milestones.md           ← (Optional) Milestone descriptions
├── environment/
│   ├── Dockerfile          ← Container the agent works in
│   └── docker-compose.yaml ← (Optional) Multi-container config
├── solution/
│   └── solve.sh            ← Oracle solution (shell script)
└── tests/
    ├── test.sh             ← End-to-end test runner
    └── outputs.py          ← Python unit tests (test_outputs.py)
```

You **do not** create the rubric as a local file — it is generated automatically on the Snorkel Expert Platform during submission.

---

## 5. File-by-File Breakdown

### `instruction.md` — The Agent Prompt

This is the natural-language prompt given to the AI agent. Think of it like how you'd type a message into Claude Code or Cursor.

**Rules:**
- Keep it **1–3 paragraphs** (succinct)
- Write it **naturally** — not always bullet points and headers
- Vary the tone: sometimes formal and structured, sometimes casual and conversational
- Must be **fully self-contained** — the agent should understand exactly what to do without additional input
- Cover all milestones if your task has them

**Good example styles:**
- A casual paragraph: *"Hey, I need you to download the CIFAR-10 dataset and train a basic classifier on it. Save the final accuracy to results.txt."*
- A more structured prompt with numbered steps
- A mix of both — whatever feels like real-world engineer behavior

---

### `task.toml` — Task Metadata

A configuration file with key information about your task. Fields include:

```toml
title = "Your Task Title"
category = "Software Engineering"
subcategories = ["api_integration", "database_interaction"]
codebase_size = "small"          # minimal | small | large
number_of_milestones = 3         # 0 if no milestones
difficulty = "medium"            # easy | medium | hard
language = "Python"
forked_repo = ""                 # name + commit hash if forking open-source
```

**Key rules:**
- `number_of_milestones` must always be present — set to `0` if no milestones
- `subcategories` can be empty, one value, or multiple values
- If you fork an open-source repo, include its name and commit hash

---

### `environment/Dockerfile` — The Docker Container

Defines the Linux environment the agent works inside.

**Rules:**
- Only ubuntu/debian-based images are supported
- Do NOT install test dependencies here — those go in `test.sh`
- Do NOT copy test scripts into the image
- Must run without `--privileged` mode (no root/admin access required)
- Use Terminal-Bench base images when possible:
  - Available at: https://github.com/laude-institute/terminal-bench/packages

**Minimum boilerplate if using a custom base image:**
```dockerfile
FROM {some-image-name}

RUN apt-get update && apt-get install -y tmux asciinema

WORKDIR /app
```

**For multi-container tasks** (avoid when possible), use `docker-compose.yaml`. The file must include a `client` image that the agent interacts with.

---

### `solution/solve.sh` — The Oracle Solution

A shell script that correctly and reliably completes the task from scratch.

**Rules:**
- Must pass all tests every time it runs
- Every submitted task must pass its own Oracle solution — this is a hard requirement for acceptance
- Should reflect a real, human expert approach — not a hacky workaround

---

### `tests/test.sh` — End-to-End Test Runner

A shell script that installs dependencies and verifies the agent's work.

**Rules:**
- Must always be named `test.sh`
- Must produce a reward file in the logs/verifier area of your zip folder
- Installs any test dependencies (not the Dockerfile's job)

---

### `tests/outputs.py` — Python Unit Tests

Deterministic Python unit tests that check the final state of the environment.

**Rules:**
- The file that must exist is `test_outputs.py`
- Uses pytest format
- Should cover all intended behavior described in the task instructions
- Must pass at least once across 10 agent runs for the task to be accepted

**Example:**
```python
def test_output_file_exists():
    assert Path("/app/results.txt").exists(), "results.txt not found"

def test_accuracy_logged():
    content = Path("/app/results.txt").read_text()
    assert "accuracy" in content.lower(), "Accuracy not logged"
```

---

### `milestones.md` — Milestone Descriptions (Optional)

A plain text/markdown file describing each milestone in order. Only include this if your task uses milestones.

---

## 6. Task Requirements

Your task must meet ALL of these to be accepted:

- **Multi-step** — requires multiple commands/actions; not solvable in one shot
- **Testable** — unit tests can verify the final environment state deterministically
- **Fully specified** — agent can attempt the task without ambiguity
- **Standalone** — runs to completion without any user input after starting; all parameters provided via flags, files, env vars, or task.toml
- **No privileged access** — must not require root or `--privileged` Docker settings
- **Terminal-based** — task must interact with the environment through the terminal (avoid pure data structures / algorithm tasks as the main focus)
- **Not trivial** — agents must fail at least some of the time (0% failure = rejected)
- **Unique** — cannot copy or closely replicate existing Terminal-Bench tasks or your own prior submissions
- **Oracle solution passes** — your solve.sh must pass all tests every run

---

## 7. Difficulty Ratings

These are determined by how often the AI agents (GPT and Claude Opus) pass the task across multiple runs:

| Difficulty | Agent Pass Rate | Notes                          |
|------------|-----------------|--------------------------------|
| Easy       | > 80%           | Acceptable but not ideal       |
| Medium     | 21% – 80%       | Great — often in demand        |
| Hard       | < 20%           | Excellent — highly valuable    |
| Trivial    | 100%            | **NOT accepted — too easy**    |

You are not paid more for harder tasks by default, but occasional bonuses are announced in Slack when specific difficulty levels are needed to balance the dataset.

---

## 8. Task Categories & Subcategories

### Categories (pick one)

Your task falls into exactly one of these domains:

| Category                    |
|-----------------------------|
| Admin                       |
| Build and Dependency Management |
| Data Processing             |
| Games                       |
| Software Engineering        |
| Machine Learning            |
| Debugging                   |
| Security                    |
| Scientific Computing        |

### Subcategories (pick any, or none)

These are additional descriptors — your task can match one, multiple, or none:

| Subcategory           | When to use it                                         |
|-----------------------|--------------------------------------------------------|
| `long_context`        | Task challenges large context windows                  |
| `tool_specific`       | Task uses a specific tool or CLI utility               |
| `api_integration`     | Task involves calling external or local APIs           |
| `database_interaction`| Task involves reading/writing a database               |
| `ui_building`         | Task creates or modifies a user interface              |

Leave subcategories blank in `task.toml` if none apply.

---

## 9. Milestones

Milestones break a complex task into sequential sub-tasks. They are strongly encouraged in Terminus 2nd Edition.

**How they work:**
- Each milestone is a standalone step that must be completed before the next begins
- The agent must explicitly signal milestone completion before the framework validates it
- Each milestone needs its own unit test verifier
- The environment must remain stable between milestone validations

**What to include when using milestones:**

| File/Field | What to do |
|---|---|
| `instruction.md` | List and describe all milestones clearly |
| `tests/outputs.py` | Include verifiers aligned to each milestone |
| `task.toml` | Set `number_of_milestones` to the correct count |
| `milestones.md` | Add this file with milestone descriptions |
| Rubric | Ensure rubric covers all milestones, not just the first |

**Example milestone flow:**
1. Set up a PostgreSQL database with a specific schema
2. Import a CSV dataset into the database
3. Write a query script that exports aggregated results to a file
4. Validate the output file format and contents

---

## 10. The Rubric

The rubric is a scoring guide that evaluates the *quality* of the agent's approach — beyond just pass/fail.

**How it works:**
- Generated automatically on the Snorkel Expert Platform (not a local file)
- You review and edit it for completeness and accuracy
- It awards points for positive steps and penalizes bad ones

**Scoring rules:**
- Scores are always: **+1, +2, +3, +5** (positive) or **-1, -2, -3, -5** (negative)
- **Never use 4** — the number 4 is not a valid rubric score
- One score per rubric item

**Example rubric items:**

| Action | Score |
|---|---|
| Agent includes error handling and reports failures clearly | +1 |
| Agent keeps data processing logic data-driven, avoids hard-coding values | +3 |
| Agent uses an efficient algorithm appropriate to the data size | +2 |
| Agent deletes required output files before completing | -3 |
| Agent runs `rm -rf /` or similarly destructive command | -5 |

**When using milestones:** Ensure rubric items cover all milestones, not just the first one.

---

## 11. Diversity Rules

To keep the dataset balanced, follow these limits:

| Rule | Limit |
|---|---|
| Python-based tasks | No more than **50%** of your submissions |
| FastAPI tasks | No more than **10%** — avoid it generally |
| Multi-container tasks | No more than **10%** — prefer single-container |

**Codebase size — aim for variety across your submissions:**

| Size | Definition |
|---|---|
| `minimal` | Little to no code context (0–20 files in environment) |
| `small` | A smaller set of scripts (20+ files) |
| `large` | Production or near-production scale (200+ files) |

Currently, **large** codebase tasks are in high demand. If you can fork a real open-source repo, do it — just include the repo name and commit hash in `task.toml`.

**Also vary:**
- Programming languages used
- Instruction prompt style (casual vs structured)
- Number of files/resources included with the task
- Task domains and subcategories across submissions

---

## 12. Choosing the Right Task Skeleton

Task skeletons are pre-built folder structures you download and fill in — so you never start from scratch.

| Your task... | Use this skeleton |
|---|---|
| Has milestones | **Milestone task skeleton** |
| Involves UI building | **UI task skeleton** |
| Neither of the above | **Regular task skeleton** (default) |

Skeletons are available:
- In the Slack channel → Resources tab at the top
- On the project website → Platform Submission section

---

## 13. Step-by-Step Submission Workflow

### Stage 1: Build Locally

1. Download the correct task skeleton
2. Rename the task folder to your task name
3. Write your `instruction.md` prompt
4. Build your `environment/Dockerfile`
5. Write your Oracle solution in `solution/solve.sh`
6. Write unit tests in `tests/outputs.py` and `tests/test.sh`
7. Fill in all fields in `task.toml`
8. If using milestones, add `milestones.md`
9. Test your Oracle solution locally — it must pass all tests
10. Zip up the entire task folder

### Stage 2: Submit to Platform

1. Log into the Snorkel Expert Platform
2. Find the **Terminus 2nd Edition** project
3. Go to the **Submission node** and click **Start**
   - (Ignore the Review node unless you're a reviewer)
4. Upload your zip file

### Stage 3: LLM-as-a-Judge (LMaJ) Checks

5. Click the **Run Feedback** button to trigger LMaJ checks
6. Wait 1–2 minutes for results
7. Review the output — green = passing
8. If anything fails: edit locally → re-zip → re-upload → re-run checks
9. Note: LMaJ checks use AI so results are non-deterministic — if you strongly disagree with a result, you can proceed, but aim to pass most checks

### Stage 4: CI Checks

10. Check the **Generate Rubric** checkbox (rubric will be generated when CI runs)
11. Make sure **Send to Reviewer is NOT checked**
12. Click **Submit** — this sends your task for CI evaluation (runs in the cloud)
13. Wait ~10–15 minutes
14. Check your **Snorkel homepage** → Tasks to Be Revised section
15. Click **Revise** when it appears
16. Review CI results (Difficulty Check and Quality Check sections now populated)
17. If anything fails: iterate locally → re-zip → re-upload → resubmit for CI

### Stage 5: Edit Your Rubric

18. Once CI results are back, your rubric will be auto-populated
19. Review it carefully — add missing items, remove inaccurate ones, adjust scores
20. Ensure rubric covers all milestones if applicable

### Stage 6: Peer Review

21. Once all checks pass and rubric looks good:
22. Check **Send to Reviewer** checkbox
23. Click **Submit** — now goes to a human reviewer
24. Reviewer either **accepts** or **sends back with feedback**
25. If sent back: make changes, resubmit
26. If you disagree with reviewer feedback: check the dispute box, explain your reasoning in the text field, and resubmit

---

## 14. Quality Checks Explained

### LLM-as-a-Judge (LMaJ) Checks

Run instantly on the platform. Check for non-deterministic quality indicators, including:

- Does the task description match the test behavior?
- Do tests cover all intended behavior?
- Are test docstrings informative?
- Are there anti-cheating measures?
- Is structured data schema correct?
- Are dependencies pinned?
- Are there typos?
- Does the solution reference hard-coded file paths?

### CI (Continuous Integration) Checks

Run in the background (~10–15 min). Check for:

- Correct task fields present in `task.toml`
- No privileged container settings
- Task file sizes within limits
- PR files are correct
- Absolute paths (avoid these — use relative paths)
- Dockerfile correctness
- Test sanity checks
- Solution image validity

---

## 15. Peer Review Process

A human engineer reviews your submission for overall quality. They can:

- **Accept** — task is finalized and compensated
- **Request revisions** — you'll see feedback on the left side of the submission page; make changes and resubmit

**If you receive bad feedback:**
- Dispute it using the dispute checkbox + text field
- Flag it to Snorkel in Slack so the reviewer can be corrected

Human reviewers can make mistakes — you have the right to push back with reasoning.

---

## 16. Compensation & Office Hours

### Compensation

- **$250 per accepted submission** (current rate as of this guide)
- Rate subject to change — watch the Slack Announcements channel
- Occasional **bonuses** for specific diversity needs (e.g., more mediums, more large codebases, specific languages)

### Office Hours

- Held **3 days per week** (schedule in Slack Announcements)
- Drop in/out freely during the 1-hour session
- Snorkel staff + technical resources available for questions
- Not mandatory — use Slack if you prefer async help

### Slack Channels

- **Terminus 2nd Edition Submission** — ask questions, report bugs, get help
- **Terminus 2nd Edition Announcements** — read-only; important project updates from Snorkel

---

## 17. Quick Reference Checklists

### Before Submitting

- [ ] `instruction.md` written naturally, 1–3 paragraphs
- [ ] `task.toml` fully filled in (all required fields)
- [ ] `environment/Dockerfile` builds without errors
- [ ] Docker runs without `--privileged`
- [ ] `solution/solve.sh` passes all tests reliably
- [ ] `tests/test.sh` produces a reward/result file
- [ ] `tests/outputs.py` (test_outputs.py) covers all intended behavior
- [ ] If milestones: `milestones.md` present, `number_of_milestones` set
- [ ] If no milestones: `number_of_milestones = 0` in task.toml
- [ ] Task is not trivially easy (agents must fail sometimes)
- [ ] Task is unique (not copied from Terminal-Bench or prior submissions)
- [ ] No absolute paths in scripts
- [ ] Correct task skeleton used (regular / UI / milestone)

### Rubric Rules

- [ ] Covers all milestones (if applicable)
- [ ] All scores are ±1, ±2, ±3, or ±5
- [ ] No score of 4 (positive or negative)
- [ ] Positive items reward meaningful correct steps
- [ ] Negative items penalize destructive or wasteful actions

### Diversity Check

- [ ] Not using FastAPI (or keeping it under 10%)
- [ ] Not defaulting to Python if another language works
- [ ] Aiming for single-container setup
- [ ] Codebase size varies across your submissions

---

## Further Reading

- Terminal-Bench paper: https://arxiv.org/pdf/2602.21193
- Snorkel blog on Terminal-Bench 2.0: https://snorkel.ai/blog/terminal-bench-2-0-raising-the-bar-for-ai-agent-evaluation/
- Snorkel's role in building Terminal-Bench: https://snorkel.ai/blog/evaluating-coding-agent-capabilities-with-terminal-bench-snorkels-role-in-building-the-next-generation-benchmark/
- Chat with the Terminal-Bench team: https://snorkel.ai/blog/chat-with-the-terminal-bench-team/
- Harbor framework for running agents: https://harborframework.com
- OpenThoughts TB dataset on HuggingFace: https://huggingface.co/datasets/open-thoughts/OpenThoughts-TB-dev-v2

---

*This guide is based on the official Project Terminus onboarding video and publicly available Terminal-Bench documentation at tbench.ai. Always refer to the live project website and Slack channels for the most current guidelines.*
