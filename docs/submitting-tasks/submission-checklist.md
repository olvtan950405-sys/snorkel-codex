# Submission Checklist

Use this checklist before every submission to ensure your task is complete and will pass review.

> **For detailed requirements:** See [Task Requirements](/portal/docs/understanding-tasks/task-requirements) for complete specifications on each component.

---

## Pre-Submission Verification

### Task Design

- [ ] Problem statement is clear and unambiguous
- [ ] All requirements are explicitly stated
- [ ] Uses absolute paths (e.g., `/app/file.txt`)
- [ ] Output files are named in instructions
- [ ] Data schemas are fully specified
- [ ] Difficulty target: < 80% pass rate

### Required Files

**Always required:**
- [ ] `task.toml` — Complete configuration with all required sections ([requirements](/portal/docs/understanding-tasks/task-requirements#tasktoml-requirements))
- [ ] `environment/Dockerfile` — Builds successfully; language dependencies pinned, every `FROM` image digest-pinned, final runtime base canonical (or non-canonical with a justification), and `environment/` within size limits ([requirements](/portal/docs/understanding-tasks/task-requirements#dependency-pinning))

**Non-milestone tasks** (`number_of_milestones = 0`):
- [ ] `instruction.md` — Clear, human-written instructions ([requirements](/portal/docs/understanding-tasks/task-requirements#instructionmd-requirements))
- [ ] `environment/Dockerfile` — Builds successfully; application dependencies pinned to exact versions; all base images use `@sha256:<digest>` pins ([requirements](/portal/docs/understanding-tasks/task-requirements#dependency-pinning))
- [ ] `solution/solve.sh` — Deterministic, human-written solution ([requirements](/portal/docs/understanding-tasks/task-requirements#solution-requirements))
- [ ] `tests/test.sh` — Runs Python pytest tests with pre-installed verifier dependencies and produces reward file ([requirements](/portal/docs/understanding-tasks/task-requirements#test-requirements))
- [ ] `tests/test_outputs.py` — Python pytest tests with docstrings that verify behavior

**Milestone tasks** (`number_of_milestones >= 2`) — see the [Milestones page](/portal/docs/understanding-tasks/milestones) for the full layout:
- [ ] `task.toml` includes one `[[steps]]` block per milestone (count must equal `number_of_milestones`)
- [ ] No root-level `instruction.md`, `tests/`, `solution/`, or `milestone_x.md` files
- [ ] For each milestone `N`, a `steps/milestone_N/` directory containing:
  - [ ] `instruction.md` — prompt for milestone `N` only (milestone 1 should include the overall task context)
  - [ ] `tests/test.sh` — milestone `N`'s test runner
  - [ ] `tests/test_mN.py` — pytest assertions scored only against milestone `N`
  - [ ] `solution/solve.sh` — wrapper that runs `solveN.sh`
  - [ ] `solution/solveN.sh` — oracle solution scoped only to milestone `N`

### Rubric
- Every submission should include a rubric that is aligned to the task. 
- You generate a synthetic rubric via the submission UI in the Snorkel Platform, then edit it for accuracy and completeness.
- The rubric must include **at least three** criteria that assign **negative** rewards (for example, `-1`).
- See the  [Rubrics page](/portal/docs/understanding-tasks/rubrics) for workflow details and quality criteria.

### Quality Standards

- [ ] All requirements have corresponding tests
- [ ] All tests verify described requirements with complete coverage of the prompt (explicit, implicit, and edgecases.)
- [ ] Tests are written in Python and run with pytest
- [ ] Anti-cheating measures in place (no hints or exposed answers)
- [ ] Tests check behavior, not implementation
- [ ] Complies with [Quality Guidelines](/portal/docs/reference/quality-guidelines)

---

## Automated Checks

### Oracle Agent

```bash
stb harbor run -a oracle -p <task-folder>
```

- [ ] Oracle agent PASSES

### CI Checks

```bash
stb harbor tasks check <task-folder> -m openai/@openai/gpt-5.5
```

- [ ] pinned_dependencies ✓
- [ ] check_pinned_images ✓
- [ ] check_sanctioned_base_images ✓
- [ ] check_build_context_size ✓
- [ ] typos ✓
- [ ] tests_or_solution_in_image ✓
- [ ] check_dockerfile_references ✓
- [ ] check_test_sh ✓
- [ ] check_task_absolute_path ✓
- [ ] check_privileged_containers ✓
- [ ] ruff ✓
- [ ] check_task_sizes ✓
- [ ] validate_task_fields ✓

Warnings should also be fixed unless an explicit reviewer-approved exception applies:

- [ ] check_dockerignore (warn)
- [ ] check_dockerfile_hygiene (warn)
- [ ] check_offline_tests (warn)
- [ ] check_apt_usage (warn)
- [ ] check_reproducible_builds (warn)
- [ ] check_layer_volatility (warn)
- [ ] check_no_build_tools_in_runtime (warn)
- [ ] check_file_extraction (warn)
- [ ] check_heredoc_usage (warn)
- [ ] check_recursive_permissions (warn)

### LLMaJ Checks

- [ ] behavior_in_task_description ✓
- [ ] behavior_in_tests ✓
- [ ] informative_test_docstrings ✓
- [ ] anti_cheating_measures ✓
- [ ] structured_data_schema ✓
- [ ] hardcoded_solution ✓
- [ ] file_reference_mentioned ✓

---

## Real Agent Testing

### Run Against GPT-5.5

```bash
stb harbor run -m @openai/gpt-5.5 -p <task-folder>
```

- [ ] Run 1: PASS / FAIL
- [ ] Run 2: PASS / FAIL
- [ ] Run 3: PASS / FAIL

### Run Against Claude Opus 4.8

```bash
stb harbor run -m @anthropic/claude-opus-4-8 -p <task-folder>
```

- [ ] Run 1: PASS / FAIL
- [ ] Run 2: PASS / FAIL

### Difficulty Calculation

| Difficulty | Threshold | Description |
|------------|-----------|-------------|
| **Hard** | Accuracy ≤ 20% on the **best** model, OR ≤ 20% on the **worst** model | Requires deep expertise, multi-step reasoning |
| **Medium** | 20% < accuracy ≤ 60% on the **worst** model | Moderate complexity, some domain knowledge |
| **Easy** | 60% < accuracy ≤ 80% on the **worst** model | Straightforward but still non-trivial |

- Worst-model pass rate: ____%
- Best-model pass rate: ____%
- Difficulty: Easy / Medium / Hard

> Tasks where the worst model scores above 80% will not be accepted. Full criteria: [Difficulty Guidelines](/portal/docs/understanding-tasks/difficulty-guidelines).

---

## Final Review

Use the [Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist) to validate your task against the same criteria reviewers use before you submit.

### Self-Check Questions

1. **Would I understand this task as a first-time reader?**
   - If no → Clarify instructions

2. **Are there any ambiguous requirements?**
   - If yes → Make them explicit

3. **Could an agent cheat on this task?**
   - If yes → Add anti-cheating measures

4. **Do tests verify actual behavior?**
   - If no → Rewrite to test behavior

5. **Is the solution deterministic?**
   - If no → Add seeds, remove randomness

---

## Submission Method

- [ ] Created ZIP of files (not folder)
- [ ] All required files included in ZIP
- [ ] Uploaded to terminus-project-v2 on Snorkel Expert Platform
- [ ] Metadata filled in

See [Platform Submission Guide](/portal/docs/submitting-tasks/platform-submission) for detailed submission steps.

---

## Ready?

If you've completed all items above, upload your ZIP file to the Snorkel Expert Platform.

**Good luck!** 🎉

---

## Need Help?

- Slack: `#ec-terminus-submission`
- [Reviewer Checklist](/portal/docs/reviewing-tasks/reviewer-checklist)
- [Troubleshooting guide](/portal/docs/reference/troubleshooting)
- [FAQ](/portal/docs/reference/faq)
