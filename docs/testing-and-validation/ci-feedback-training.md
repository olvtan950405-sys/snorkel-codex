# CI Feedback Training

Learn to iterate on CI and LLMaJ feedback to get your task passing all checks.

## Video Tutorial

<video-loom id="db35a5b03c1c43ab80f46f481fa02be1" title="CI Feedback Training"></video-loom>

## Practice Notebook

Download the Jupyter notebook for hands-on practice:

<pdf-download src="/Terminus-EC-Training-stateful/ci_feedback_training.ipynb" title="Download CI Feedback Training Notebook"></pdf-download>

## What You'll Learn

- Understanding CI check output
- Interpreting LLMaJ feedback
- Iterating on failures efficiently
- Common patterns and fixes

## CI Iteration Workflow

```
Run checks → Identify failures → Fix issues → Re-run → Repeat
```

### Step 1: Run All Checks

```bash
stb harbor tasks check <task-folder> -m openai/@openai/gpt-5.5
```

### Step 2: Review Output

```
CI Checks:
  ✓ pinned_dependencies
  ✗ check_task_absolute_path
  ✓ validate_task_fields

LLMaJ Checks:
  ✓ behavior_in_tests
  ✗ informative_test_docstrings
  ✓ anti_cheating_measures

2 checks failed
```

### Step 3: Fix One Issue at a Time

Focus on one failure at a time. The error message will tell you exactly what's wrong:

```
✗ check_task_absolute_path
  Line 3: "Edit config/settings.json"
  Use absolute path: /app/config/settings.json
```

> **For detailed fix instructions:** See [CI Checks Reference](/portal/docs/testing-and-validation/ci-checks-reference) and [LLMaJ Checks Reference](/portal/docs/testing-and-validation/llmaj-checks-reference)

### Step 4: Re-run and Verify

```bash
stb harbor tasks check <task-folder> -m openai/@openai/gpt-5.5
```

### Step 5: Repeat

Continue fixing issues one at a time until all checks pass.

## Understanding Error Messages

Error messages are designed to be helpful. They typically include:
- **Which check failed** (e.g., `check_task_absolute_path`)
- **Where the issue is** (file and line number)
- **What's wrong** (specific problem description)
- **How to fix it** (suggestion or requirement)

Read the error message carefully—it tells you exactly what needs to be fixed.

## Tips for Efficient Iteration

1. **Fix easy issues first** — Start with CI checks (syntax/structure) before LLMaJ (quality)

2. **Run locally before submitting** — Saves time and helps you catch issues early

3. **Read error messages carefully** — They tell you exactly what's wrong and often how to fix it

4. **One fix at a time** — Easier to track what worked and debug if something breaks

5. **Use the reference guides** — [CI Checks Reference](/portal/docs/testing-and-validation/ci-checks-reference) and [LLMaJ Checks Reference](/portal/docs/testing-and-validation/llmaj-checks-reference) have detailed explanations for each check

## Checklist Before Final Submission

- [ ] All CI checks pass
- [ ] All LLMaJ checks pass
- [ ] Oracle agent passes
- [ ] Real agents tested (difficulty verified)
- [ ] Code reviewed for quality

---

## Next Steps

- [Submit via Platform](/portal/docs/submitting-tasks/platform-submission)

