# Welcome to Project Terminus

## Changelog


| Date         | Type      | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------ | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Jul 10, 2026 | 🔄 Update | **The `data-processing` category is currently blocked.** Data Processing & Scripting is paused — not accepting new submissions, and it has been removed from the task gallery. Do not submit new tasks under this category until this note is removed. Tasks already in your revision queue or awaiting review are exempt and continue through to Accepted as normal. ***[See Task Taxonomy](/portal/docs/understanding-tasks/task-taxonomy)*** |
| Jul 9, 2026  | 🔄 Update | **`gpus`, `gpu_types`, and `docker_flags` in `task.toml` `[environment]` are optional.** Tasks will not be sent back for omitting these or leaving them blank — TB2 tasks are not required to use GPU. Both the full and minimal `[environment]` blocks are valid. ***[See Dockerfile Best Practices](/portal/docs/creating-tasks/dockerfile-best-practices)*** |
| Jun 29, 2026 | 🔄 Update | **New milestone tasks and the `debugging` / `software-engineering` categories are currently blocked.** Net-new submissions in these areas are rejected by an eval check. Milestone tasks already in your revision queue or awaiting review are exempt and continue through to Accepted as normal. ***[See Task Taxonomy](/portal/docs/understanding-tasks/task-taxonomy)*** and ***[Milestones](/portal/docs/understanding-tasks/milestones)*** |
| Jun 12, 2026 | 🆕 New    | Added the **canonical Terminal-Bench base image list** to the Dockerfile Best Practices guide — a curated set of 10 digest-pinned images covering Python, Node, Go, Rust, Java, Ruby, C/C++ (GCC), Maven, Debian, and Ubuntu. Prefer these for the final runtime stage to maximize reusability and cache hits. Non-canonical images are still allowed with a brief, credible justification in the Dockerfile or task `README.md`; missing or vague justifications are now blocked. ***[See Dockerfile Best Practices §2](/portal/docs/creating-tasks/dockerfile-best-practices)*** |
| Jun 12, 2026 | 🔄 Update | **Difficulty-check models upgraded.** Tasks are now benchmarked against **Claude Opus 4.8** and **GPT-5.5** (previously Claude Opus 4.6 and GPT-5.2). Difficulty thresholds and EASY/MEDIUM/HARD ratings are unchanged — only the benchmark models changed. Since the new models are stronger, tasks that previously rated MEDIUM or HARD may land differently; calibrate accordingly. GPT-5.5 is also now available in the EC CLI. ***[See Difficulty Guidelines](/portal/docs/understanding-tasks/difficulty-guidelines)*** |
| Jun 3, 2026  | 🆕 New    | Added an **Environment Problems** section to the Common Errors reviewer reference covering Dockerfile/container defect patterns: missing `tmux`/`asciinema`, runtime network installs in `test.sh`, AI-scaffolding filenames, solution/tests baked into the image, privileged mode, reserved-directory conflicts, oversized build context, and unsanctioned base images. Each section of Common Errors now also names its corresponding reviewer feedback category. ***[See Common Errors](/portal/docs/reviewing-tasks/common-errors)*** |
| Jun 3, 2026  | 🔄 Update | Restored the defensive `rc=$?` variable form in the `tests/test.sh` canonical example. The `check_test_sh` CI gate now accepts **both** the literal `$?` inline form and a variable captured from `$?` immediately after pytest. The variable form is preferred because `$?` only holds the last command's exit status, so any line between pytest and the conditional silently clobbers it. ***[See Writing Tests](/portal/docs/creating-tasks/writing-tests)*** |
| Jun 3, 2026  | 🔄 Update | Clarified rubric formatting: **milestone tasks** must split the rubric into one block per milestone using `# Rubric 1`, `# Rubric 2`, etc. header lines (the CI parser is aligned to this format). **Non-milestone tasks** use a flat list of `Agent …, ±N` lines; a single `# Rubric 1` header is tolerated but not required. ***[See Rubrics](/portal/docs/understanding-tasks/rubrics)*** |
| Jun 3, 2026  | 🔄 Update | **`codebase_size = "minimal"` tasks are accepted again** (re-allowed as of May 11, 2026). CI checks no longer block them. Updated the FAQ codebase-size table and Diversity Requirements page to reflect this. ***[See FAQ](/portal/docs/reference/faq)*** |
| May 27, 2026 | 🔄 Update | Dockerfile CI checks now block tag-only `FROM` images, unsanctioned final runtime bases, and oversized `environment/` build contexts. Every `FROM` image must include `@sha256:<digest>`, the final runtime base must be sanctioned or exempt, and `environment/` must stay within 100 MiB total / 50 MiB per file. Dockerfile hygiene, offline verifier setup, apt usage, reproducible downloads, layer ordering, build-tool cleanup, archive extraction, heredocs, and recursive permissions are documented as warnings by default. ***[See CI Checks Reference](/portal/docs/testing-and-validation/ci-checks-reference)*** |
| May 27, 2026 | 🔄 Update | Clarified the `tests/test.sh` reward block: the `if/else` reward write is the canonical end of the script — **no trailing `exit` is required or desired**. Harbor reads `/logs/verifier/reward.txt`, not the script exit code, and the `check_test_sh` gate enforces this shape. Reviewers must not flag a missing `exit`. Also replaced the stale `test.sh` example in the Platform Submission guide that showed `apt-get`/`curl` installs (contradicted `allow_internet = false`). ***[See Writing Tests](/portal/docs/creating-tasks/writing-tests)*** |
| May 27, 2026 | 🆕 New    | Added a new High-severity Reviewer Checklist criterion: the task **environment** (files, comments, READMEs, configs, scripts, TODOs) must not contain hidden step-by-step walkthroughs or solution hints. ***[See Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist)*** |
| May 27, 2026 | 🆕 New    | Added guidance closing the "spec.md loophole": environment spec/doc files must not contain step-by-step solution guides, must not be used to split instructions out of `instruction.md` to dodge length limits, and must read like realistic engineering documents (not LLM-style prompt extensions). ***[See Prompt Styling](/portal/docs/understanding-tasks/prompt-styling)*** |
| May 19, 2026 | 🔄 Update | Added "No AI-framework scaffolding filenames" criterion to the Reviewer Checklist (Environment section, High severity). Filenames like `CLAUDE.md` or `skills.md` indicate incomplete cleanup and should not appear in task environments. ***[See Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist)***                                                                                                                                                                                                                                                                                                     |
| May 15, 2026 | 🆕 New    | Added a **Large Codebase Tasks** section to the Task Gallery. Each idea includes a bundled pre-built environment and verifier tests to make large codebase task creation more approachable. Go to the ***[Task Gallery](/portal/tasks)*** and scroll to the purple "Large Codebase Tasks" section.                                                                                                                                                                                                                                                                                                                            |
| May 15, 2026 | 🆕 New    | Added **Long Context Task Checklist** — a required reference for submitting or reviewing any `long_context` subtype task. ***[Go to Long Context Checklist](/portal/docs/reviewing-tasks/long-context-checklist)***                                                                                                                                                                                                                                                                                                                                                                                                           |
| May 15, 2026 | 🆕 New    | Added **Dockerfile & Image Best Practices** guide covering digest pinning, reproducible builds, layer ordering, network isolation, multi-stage builds, and more. ***[Go to Dockerfile Best Practices](/portal/docs/creating-tasks/dockerfile-best-practices)***                                                                                                                                                                                                                                                                                                                                                               |
| May 15, 2026 | 🔄 Update | `allow_internet = false` is now required in every `task.toml` under `[environment]`. All verifier/test dependencies must be pre-installed in the Dockerfile — `test.sh` must not install packages or fetch from the network at runtime. Task skeletons (default, milestone, UI) have been updated to reflect this. ***[See Platform Submission guide](/portal/docs/submitting-tasks/platform-submission)***                                                                                                                                                                                                                   |
| May 4, 2026  | 🔄 Update | Milestone task structure migrated to the Harbor multi-step format: - Each milestone now lives in its own subdirectory under `steps/milestone_N/` with its own `instruction.md`, `tests/`, and `solution/`. - `task.toml` declares one `[[steps]]` block per milestone. - Root-level `instruction.md`, `tests/`, `solution/`, and `milestone_x.md` files are no longer used in milestone tasks. - The previous milestone format (root-level `solveN.sh`, `test_mN.py`, `milestone_x.md`) is deprecated. - ***[See details in Milestones page](/portal/docs/understanding-tasks/milestones)***                                  |
| May 4, 2026  | 🔄 Update | Superseded by the May 27 Dockerfile CI update: base images now require digest pins again. Application dependencies (pip, npm, etc.) still must be pinned to exact versions. ***[See Docker environment guide](/portal/docs/creating-tasks/creating-docker-environment#1-pin-dependencies-and-base-images)***                                                                                                                                                                                                                                                                                                                 |
| Apr 20, 2026 | 🔄 Update | Revamped the FAQ. ***[Go to FAQ page](/portal/docs/reference/faq)***                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Apr 15, 2026 | 🆕 New    | Added 3 new walkthrough training videos to onboarding page covering submissions, revisions, and general information. ***[Go to onboarding page](/portal/docs/onboarding/platform-onboarding)***                                                                                                                                                                                                                                                                                                                                                                                                                               |
| Apr 6, 2026  | 🔄 Update | Clarified test coverage: tests must fully cover the prompt—explicit requirements, implicitly expected behavior, and critical edge cases—with every prompt requirement mapped to a test. ***[Go to Writing Tests page](/portal/docs/creating-tasks/writing-tests)***                                                                                                                                                                                                                                                                                                                                                           |
| Apr 3, 2026  | 🆕 New    | Milestone tasks must now include separate `milestone_1.md`, `milestone_2.md`, etc. files: - Each file contains the description of what is to be achieved in that milestone. - `instructions.md` must still include descriptions of all milestones as before. - `milestone_1.md` should include the general task description paragraph along with Milestone 1 content. - Remaining `milestone_x.md` files contain their respective milestone descriptions. - In short, your `milestone_x.md` files are your `instructions.md` sliced up. - ***[See details in Milestones page](/portal/docs/understanding-tasks/milestones)*** |
| Apr 2, 2026  | 🔄 Update | Minor documentation clarifications: - `codebase_size` counts all files in the task environment (excluding files the agent produces). - `author_name` and `author_email` may be set to `"anonymous"`.                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Apr 2, 2026  | 🆕 New    | Added ***[Submission Diversity Requirements page](/portal/docs/understanding-tasks/diversity-requirements)***.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| Apr 1, 2026  | 🆕 New    | Added ***[Reviewer Checklist page](/portal/docs/reviewing-tasks/reviewer-checklist)*** for reference when submitting and reviewing tasks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Mar 31, 2026 | 🔄 Update | Milestone tasks must: - Include `solution/solve1.sh`...`solution/solveN.sh`, where `N` is the total number of milestones. - Include a single `solution/solve.sh` that chains milestone solutions in order (`solve1.sh` -> ... -> `solveN.sh`). - Include `tests/test_m1.py`...`tests/test_mN.py` where each `test_mX.py` scores only milestone `X`.                                                                                                                                                                                                                                                                           |
| Mar 29, 2025 | 🆕 New    | Added changelog to the Welcome page.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| Mar 29, 2025 | 🐛 Fix    | Removed Canary String references. Do not include!                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Mar 29, 2025 | 🔄 Update | Rubrics must contain at least 3 negative rewards. See Rubrics section.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Mar 29, 2025 | 🔄 Update | All base images must be pinned. See Dockerfile section.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| Mar 29, 2025 | 🐛 Fix    | Fixed commands to run agents in Testing Agent Performance section                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |


## What is Project Terminus?

Project Terminus is a benchmark for evaluating AI coding agents on real-world engineering tasks. Your job is to create tasks that challenge today's best models—tasks that require genuine engineering reasoning, multi-step problem solving, and practical skills.

Unlike simple code completion benchmarks, Project Terminus tests:

- **Multi-step reasoning** — Tasks require chaining multiple commands
- **Environment interaction** — Agents work in real Docker containers
- **Practical skills** — Real debugging, configuration, and development tasks

> **Your work matters.**
>
> Every accepted task directly advances the development of AI coding agents by revealing their current limitations and pushing them to improve.

> **Explore existing tasks:** [Browse our Task Gallery](https://snorkel-ai.github.io/Terminus-EC-Training-stateful/portal/tasks)
>
> *Note: While this project is NOT affiliated with the official Terminal-Bench project, we closely mimic its style.*

## Your Role as a Coding Expert

As a Coding Expert, you will:

1. **Design tasks** that challenge frontier AI models
2. **Write oracle solutions** that demonstrate correct completion
3. **Create tests** that verify task completion
4. **Iterate on feedback** from automated checks and peer review

Task Difficulty Targets

Testing your task on AI agents on GPT-5.5 and Claude Opus 4.8 yields pass rates for the task you create. According to how many times it fails or succeeds, your task falls into the following difficulty tiers:


| Difficulty | Threshold                                                             | Description                                   |
| ---------- | --------------------------------------------------------------------- | --------------------------------------------- |
| **Hard**   | Accuracy ≤ 20% on the **best** model, OR ≤ 20% on the **worst** model | Requires deep expertise, multi-step reasoning |
| **Medium** | 20% < accuracy ≤ 60% on the **worst** model                           | Moderate complexity, some domain knowledge    |
| **Easy**   | 60% < accuracy ≤ 80% on the **worst** model                           | Straightforward but still non-trivial         |


> **Important:** Tasks where the **worst** model scores above 80% will **NOT** be accepted. See [Difficulty Guidelines](/portal/docs/understanding-tasks/difficulty-guidelines) for the full breakdown.



Evaluation Process

Each task undergoes a rigorous 4-step review:

1. **Automated CI checks** — Technical requirements (syntax, structure, etc.)
2. **LLM-as-Judge (LLMaJ)** — Quality evaluation using GPT-5.5
3. **Peer review** — Human expert verification
4. **Agent evaluation** — Run against GPT-5.5 and Claude Opus 4.8 (5 times each)



Estimated Time

- **Per task:** 2-5 hours
- **Includes:** Design, development, testing, and iteration



## Quick Links


| Resource                                                                              | Description                                 |
| ------------------------------------------------------------------------------------- | ------------------------------------------- |
| **[Quick Start Guide](/portal/docs/getting-started/quick-start)**                     | Get up and running in 10 minutes            |
| **[What Makes a Good Task](/portal/docs/understanding-tasks/what-makes-a-good-task)** | Learn to create high-quality tasks          |
| **[Task Components](/portal/docs/understanding-tasks/task-components)**               | Understand the required files and structure |
| **[FAQ](/portal/docs/reference/faq)**                                                 | Common questions answered                   |


## Need Help?


| Resource          | Link                                                                                    |
| ----------------- | --------------------------------------------------------------------------------------- |
| **Slack Channel** | `#terminus-2nd-edition-submission`                                                      |
| **Office Hours**  | Daily sessions during the week to answer questions, or get live help from Snorkel staff |


---

**Ready to dive in?**
**[Start with the Quick Start Guide](/portal/docs/getting-started/quick-start)**
