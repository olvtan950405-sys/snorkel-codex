# Oracle Agent

The Oracle Agent runs your solution/solve.sh in the task environment and verifies it passes all tests. It's the first line of validation for your task.

The Oracle Agent will be run 3 times.

## Getting Started

### Video Tutorial

New video coming soon...

### Practice Notebook

Download the Jupyter notebook for hands-on practice:

New Juypter notebook coming soon...

### What You'll Learn

- What the Oracle Agent is and how it works
- How to run the Oracle Agent on your task
- How to interpret Oracle output
- How to debug failing runs
- How to iterate and fix issues

---

## What is the Oracle Agent?

The Oracle Agent is an automated agent that:
1. Starts your Docker environment
2. Executes your solution/solve.sh commands
3. Runs your tests to verify completion
4. Reports pass/fail results

If the Oracle Agent can't complete your task, neither can AI agents.

> **Key Concept:** The Oracle Agent verifies that your task is **solvable**. If the Oracle can't solve your task, it's broken.

## Running the Oracle Agent

```bash
# Basic run
stb harbor run -a oracle -p <task-folder>

# With verbose output
stb harbor run -a oracle -p <task-folder> -v
```

## Expected Output

### Successful Run

```
Starting task: my-task
Building Docker environment...
Running oracle solution...
  ✓ Step 1 completed
  ✓ Step 2 completed
  ✓ Step 3 completed
Running tests...
  ✓ test_output_exists PASSED
  ✓ test_format_correct PASSED
  ✓ test_values_valid PASSED

RESULT: PASS
```

### Failed Run

```
Starting task: my-task
Building Docker environment...
Running oracle solution...
  ✓ Step 1 completed
  ✗ Step 2 failed: command not found

RESULT: FAIL
Error: Solution did not complete successfully
```

## Debugging Failures

### Debugging Workflow

When the Oracle Agent fails, follow this workflow:

**Step 1: Identify the Failure**
- Read the error message carefully
- Which step failed?
- What was the error?
- What file/command was involved?

**Step 2: Reproduce Interactively**
```bash
stb harbor tasks start-env -p <task-folder> -i
```
Inside the container, run commands one by one to find the issue.

**Step 3: Fix and Re-test**
1. Update `solution/solve.sh` or `environment/Dockerfile`
2. Run Oracle again
3. Repeat until passing

### Solution Fails

If your solution doesn't run:

1. **Enter interactive mode:**
   ```bash
   stb harbor tasks start-env -p <task-folder> -i
   ```

2. **Run commands manually** to find the failing step

3. **Check for:**
   - Typos in commands
   - Missing dependencies
   - Wrong file paths
   - Permission issues

### Tests Fail

If the solution runs but tests fail:

1. **Check test output** for specific failures

2. **Verify your solution** actually produces expected output

3. **Check for:**
   - Incorrect output format
   - Missing files
   - Off-by-one errors
   - Edge cases not handled

### Environment Issues

If the container won't build:

1. **Check Dockerfile syntax** in `environment/Dockerfile`

2. **Verify base image** exists and is accessible

3. **Check dependency installation** commands

4. **Try building manually:**
   ```bash
   cd <task-folder>/environment
   docker build -t test .
   ```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "command not found" | Missing dependency | Add to environment/Dockerfile |
| "file not found" | Wrong path | Use absolute paths |
| "permission denied" | File permissions | Check chmod in environment/Dockerfile |
| Tests timeout | Solution too slow | Optimize or increase timeout |

### Common Debugging Scenarios

**Missing File:**
```
Error: No such file: /app/data/input.csv
```
**Fix:** Check `environment/Dockerfile` COPY commands and file paths

**Command Not Found:**
```
Error: grep: command not found
```
**Fix:** Add package to `environment/Dockerfile` `apt-get install`

**Test Assertion Failed:**
```
AssertionError: Expected 42, got 41
```
**Fix:** Debug your solution logic

**Timeout:**
```
Error: Task exceeded timeout (1800s)
```
**Fix:** Optimize solution or increase timeout in `task.toml` (`[agent].timeout_sec`)

## Oracle vs Real Agents

| Oracle Agent | Real Agents (GPT-5.5, etc.) |
|--------------|---------------------------|
| Runs your solution/solve.sh | Generate their own solution |
| Always deterministic | May vary between runs |
| Tests task validity | Tests task difficulty |
| Must always pass | May fail (that's the goal!) |

## Best Practices

1. **Run oracle early and often** — Don't wait until submission

2. **Fix oracle failures first** — If oracle fails, task is broken

3. **Check all test output** — Understand why tests pass/fail

4. **Keep environment minimal** — Easier to debug

---

## Practice Exercise

Using the practice notebook:

1. Load the sample task
2. Run the Oracle (it will fail)
3. Identify the issue
4. Fix the solution
5. Run Oracle again until passing

---

## Next Steps

- [Run against real agents](/portal/docs/testing-and-validation/running-real-agents)
- [Review CI checks](/portal/docs/testing-and-validation/ci-checks-reference)
