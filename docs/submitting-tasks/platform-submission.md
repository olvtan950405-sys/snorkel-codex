# Platform Submission Guide

Complete step-by-step guide for creating and submitting tasks through the Snorkel Expert Platform.

## High-Level Workflow

Tasking is performed through the **Terminus-2nd-Edition** project on the Snorkel Expert Platform. The complete workflow:

1. Download the correct task skeleton template. _There are 3!_
2. Extract and rename the folder
3. Write your task instructions and configure metadata
4. Set up the Docker environment
5. Create and test your solution
6. Write and verify tests
7. Run agents 
8. Create ZIP file, check rubric generation checkbox, and Submit on platform
9. Review CI feedback and iterate + review generated rubric and edit for accuracy and completeness
10. When CI is passing, submit on platform to a reviewer

---

## Prerequisites

Before starting, ensure you have:
- Docker Desktop installed and running
- Harbor CLI installed (or access to Harbor commands)
- API key for running agents
- Access to the Snorkel Expert Platform

---

## Step 1: Download the Correct Task Skeleton

Choose and download the appropriate task skeleton template for your task type:

There are 3 task skeletons to choose from:
 - **_"Regular"_ Task Skeleton:** Use for all non-UI-Building and non-Milestone tasks
 - **UI Task Skeleton:** Use for all UI-Building subtype tasks
 - **Milestone Task Skeleton:** Use for all tasks which contain milestones

<pdf-download src="/Terminus-EC-Training-stateful/Terminus-2nd-Edition/default-template.zip" title="Download Regular Task Skeleton"></pdf-download>

<pdf-download src="/Terminus-EC-Training-stateful/Terminus-2nd-Edition/milestone-template.zip" title="Download Milestone Task Skeleton"></pdf-download>

<pdf-download src="/Terminus-EC-Training-stateful/Terminus-2nd-Edition/ui-template.zip" title="Download UI Task Skeleton"></pdf-download>


## Step 2: Extract and Rename

1. Extract the ZIP file to your desired location
2. **Rename the folder** to match your task name (use kebab-case, e.g., `fix-memory-leak-python`)

## Step 3: Write Task Instructions and Configuration

### Author your instruction.md
See the [Prompt Styling Guide](/portal/docs/understanding-tasks/prompt-styling) for detailed instructions and requirements about how you should style your instructions.

### Configure task.toml

Set up metadata and configuration:

```toml
# Task configuration schema version
version = "2.0"

# Task metadata (author, difficulty, categorization)
[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "unknown"
category = "software-engineering"
# Options for subcategories are: "long_context", "tool_specific", "api_integration", "db_interaction", "ui_building"
subcategories = [ ]
# The number of milestones in the task (can be zero if not a milestone task)
number_of_milestones = 0
# Size of the codebase: minimal -> 0-20 files, small -> 20+ files, large -> 200+ files. Include all files in the environment when counting.
codebase_size = "minimal"
# Coding languages used in the oracle solution or required by the agent
languages = [ "bash" ]
# For tool_specific, api_integration, and db_interaction subcategories, please include specific tool, api framework, or database software
tags = [ "file-operations",]
# Estimated time to complete (minutes)
expert_time_estimate_min = 60
junior_time_estimate_min = 120

# Verifier: runs the test script to check task completion
[verifier]
timeout_sec = 450.0

# Agent: limits how long the agent can run when attempting the task
[agent]
timeout_sec = 900.0

# Sandbox environment limits
[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
allow_internet = false
```

## Step 4: Configure Docker Environment

Edit the `environment/Dockerfile` to set up your task environment:

- Install `tmux` and `asciinema` — **required by the agent runtime**. Missing these will cause all agent runs to fail silently with no verifier output.
- Add any dependencies required by your task
- Pin all package versions for reproducibility
- Digest-pin every `FROM` image with `@sha256:<digest>`
- For the final runtime stage, use a [canonical Terminal-Bench base image](/portal/docs/creating-tasks/dockerfile-best-practices) when one matches your task's language. Non-canonical images are allowed with a brief written justification in the Dockerfile or task `README.md`; missing justifications are blocked.
- Keep `environment/` at or below 100 MiB total and no file over 50 MiB
- Add `.dockerignore` for non-trivial environments
- Never copy `solution/` or `tests/` folders in the Dockerfile

For multi-container environments or custom configurations, see the [Docker environment documentation](/portal/docs/creating-tasks/creating-docker-environment).

### Docker Troubleshooting

If you encounter Docker issues:

1. Ensure Docker Desktop is running
2. On macOS, enable in Advanced Settings: **"Allow the default Docker socket to be used (requires password)"**
3. Try these commands if needed:

```bash
sudo dscl . create /Groups/docker
sudo dseditgroup -o edit -a $USER -t user docker
```

## Step 5: Test Your Solution Locally

Enter your task container interactively to test your solution:

```bash
stb harbor tasks start-env -p <task-folder> -i
```

While in the container, test your solution approach to ensure it works as expected.

## Step 6: Create Solution File

Create `solution/solve.sh` with the verified commands:

- This file is used by the Oracle agent to verify the task is solvable
- Must be deterministic (same result every run)
- Should demonstrate the command sequence, not just output the answer
- For milestone tasks: each milestone has its own `steps/milestone_N/solution/` directory containing `solve.sh` (a wrapper) and `solveN.sh` (the actual oracle solution scoped only to that milestone). See the [Milestones page](/portal/docs/understanding-tasks/milestones) for the full layout.

See [Writing Oracle Solution](/portal/docs/creating-tasks/writing-oracle-solution) for guidance.

## Step 7: Write Tests

Create `tests/test.sh` and Python pytest files to verify task completion:

- The test script must run Python pytest and produce `/logs/verifier/reward.txt`
- Create Python pytest unit tests in `tests/test_outputs.py`
- Do not use `tests/test.sh` to run another language-specific test framework; Python pytest tests should drive any non-Python system under test
- Place any test fixtures or helper files in the `tests/` directory
- Bake all test dependencies into the Docker image; `tests/test.sh` must not install packages or download from the network at runtime
- For milestone tasks: each milestone has its own `steps/milestone_N/tests/` directory containing a `test.sh` runner and a `test_mN.py` pytest file (with a `TestMilestoneN` class) scored only against that milestone. See the [Milestones page](/portal/docs/understanding-tasks/milestones) for the full layout.

Tests must fully cover the prompt: explicit requirements, implicitly expected behavior, and critical edge cases—with every prompt requirement mapped to a test. See [Writing Tests](/portal/docs/creating-tasks/writing-tests) for detail.

**Example test.sh:**

```bash
#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier

# Check if we're in a valid working directory
if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

# pytest and pytest-json-ctrf must be pre-installed in the Docker image.
python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
```

See [Writing Tests](/portal/docs/creating-tasks/writing-tests) for detailed guidance.

## Step 8: Run Oracle Agent

Verify your solution passes all tests:

```bash
stb harbor run -a oracle -p <task-folder>
```

This should **PASS**. If it doesn't, fix issues before proceeding.

## Step 9: Test with Real Agents

1. Set up your API key (received via email):

```bash
export OPENAI_API_KEY=<your-portkey-api-key>
export OPENAI_BASE_URL=https://api.portkey.ai/v1
```

2. Run with GPT-5.5:

```bash
stb harbor run -m @openai/gpt-5.5 -p <task-folder>
```

3. Run with Claude Opus 4.8:

```bash
stb harbor run -m @anthropic/claude-opus-4-8 -p <task-folder>
```

Run each agent 2-3 times to gauge pass rate. Your task should have < 80% pass rate to be accepted.

## Step 10: Run LLMaJ Checks Locally

Run LLMaJ checks before submitting:

**GPT-5.5:**
```bash
stb harbor run -m @openai/gpt-5.5 -p <task-folder>
```

**Claude Opus 4.8:**
```bash
stb harbor run -m @anthropic/claude-opus-4-8 -p <task-folder>
```

All checks should pass before submission.

## Step 11: Final Verification

Before submitting, verify:

- Oracle agent passes
- All LLMaJ checks pass
- Tested against real agents (pass rate < 80%)
- All files are present and correct

Run final checks:

```bash
# Oracle agent
stb harbor run -a oracle -p <task-folder>

# LLMaJ checks
stb harbor tasks check -m openai/@openai/gpt-5.5 harbor_tasks/<task_name>
```

## Step 12: Create ZIP File

**Important:** Select the individual files inside your task folder, not the folder itself.

**Non-milestone task layout:**

```
.
├── instruction.md   ← Select these
├── task.toml       ←
├── environment/     ←
│   ├── Dockerfile   ← (or docker-compose.yaml)
│   └── [build files]
├── solution/        ←
│   └── solve.sh
└── tests/           ←
    ├── test.sh
    └── test_outputs.py
```

**Milestone task layout:**

```
.
├── task.toml       ← Select these
├── environment/     ←
│   ├── Dockerfile   ← (or docker-compose.yaml)
│   └── [build files]
└── steps/           ←
    ├── milestone_1/
    │   ├── instruction.md
    │   ├── tests/
    │   │   ├── test.sh
    │   │   └── test_m1.py
    │   └── solution/
    │       ├── solve.sh
    │       └── solve1.sh
    └── milestone_2/
        └── ... (same structure)
```

**On macOS:**
1. Open the task folder
2. Select all files (`Cmd+A`)
3. Right-click → Compress

**On Windows:**
1. Open the task folder
2. Select all files (`Ctrl+A`)
3. Right-click → Send to → Compressed folder

## Step 13: Submit to Platform

1. Go to the [Snorkel Expert Platform](https://experts.snorkel-ai.com/)
2. Navigate to **Terminus-2nd-Edition**
3. Click **Start** on the _Submission_ node
4. Upload your ZIP file
5. Keep "Send to reviewer" unchecked
6. Check the rubrics checkbox
7. Submit

## Step 14: Check CI results and rubric then Iterate until CI looks good  
1. After email notification that your submission is now back in your revision queue, go to [Snorkel Expert Platform](https://experts.snorkel-ai.com/). 
2. Find your task on homescreen
3. Click "Revise"
4. Check CI Results & update task as needed
5. Check the now generated rubric and edit it within the textbox for accuracy and completeness
5. Re-upload a new .zip file if necessary
   - Use the [Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist) to confirm you have addressed high-severity review criteria before resubmitting.
   - _If you make any significant changes to your task, you must update your rubric accordingly in order to align with the current version of your task._
6. Keep "Send to Reviewer" Unchecked 
7. Submit 

## Step 15: Submit your task to Reviewer
1. After email notification that your submission is now back in your revision queue, go to [Snorkel Expert Platform](https://experts.snorkel-ai.com/). 
2. Find your task on homescreen
3. Click "Revise"
4. Check CI results
5. Check rubric and edit for accuracy and completeness
6. If all good, check "Send to Reviewer"
7. Submit

## Step 16: Monitor Status
After submission. wait for peer review (1-7 business days)

---

## After Submission

### Review Process

1. **Automated checks** runs immediately
2. **Peer review** within 1-7 business days
3. **Feedback** provided if changes needed
4. **Acceptance** when all criteria met

### If Changes Requested

1. Review the feedback carefully
2. Make requested changes locally
3. Re-run all checks
4. Create new ZIP and resubmit

---

## Common Issues

### ZIP Structure Wrong

**Problem:** Files nested in extra folder.

**Fix:** ZIP the files directly, not the containing folder.

### Missing Files

**Problem:** Forgot to include a file.

**Fix:** Verify all files are in ZIP before uploading.

- **Non-milestone tasks:** check that `instruction.md`, `task.toml`, `environment/`, `solution/`, and `tests/` are all included.
- **Milestone tasks:** check that `task.toml`, `environment/`, and one `steps/milestone_N/` directory per milestone are all included. Each `steps/milestone_N/` must contain `instruction.md`, `tests/test.sh`, `tests/test_mN.py`, `solution/solve.sh`, and `solution/solveN.sh`. There should be **no** root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md` files.

### CI Failures After Upload

**Problem:** Local checks passed but platform CI fails.

**Fix:** Check for environment differences, re-run locally with exact CI commands.

### Docker Build Fails

**Problem:** Docker build fails on platform but works locally.

**Fix:** Ensure all application dependencies (pip, npm, etc.) are pinned to exact versions, every Docker base image (and any images in `docker-compose.yaml`) is digest-pinned with `@sha256:<digest>`, and the final runtime base image is sanctioned or explicitly exempt. Also check that `environment/` is at most 100 MiB total, no file is over 50 MiB, and platform-specific differences are handled.

---

## Video Walkthroughs

Watch these step-by-step videos to learn how to create and test your task:

### 1. Running Your Task

<video-loom id="22449b76123d41e6abff0efb39d0b960" title="Running your task"></video-loom>

### 2. Creating a solution/solve.sh
<video-loom id="140f2cf8f16d404abf5cbd7dcc66b7cb" title="Creating a solution/solve.sh"></video-loom>
The video refers to solution/solve.sh file. Using Harbor, this refers to solution/solve.sh 

### 3. Creating Tests for Your Task

<video-loom id="a00541ff2787464c84bf4601415ee624" title="Creating tests for your task"></video-loom>

---

## Next Steps

- [Understand task components](/portal/docs/understanding-tasks/task-components)
- [Review the submission checklist](/portal/docs/submitting-tasks/submission-checklist)
- [Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist)
- [Learn about CI checks](/portal/docs/testing-and-validation/ci-checks-reference)
- [Understand the review process](/portal/docs/submitting-tasks/after-submission)
