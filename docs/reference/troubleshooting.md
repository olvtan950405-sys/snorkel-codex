# Troubleshooting

Solutions to common issues you might encounter.

---

## Docker Issues

### "Cannot connect to Docker daemon"

**Cause:** Docker Desktop isn't running.

**Fix:**
1. Start Docker Desktop
2. Wait for it to fully initialize (check menu bar icon)
3. Try again

### "Permission denied" on Docker socket

**Fix (macOS):**
```bash
sudo chmod 666 /var/run/docker.sock
```

Or enable in Docker Desktop:
1. Settings → Advanced
2. Enable "Allow the default Docker socket to be used"

**Fix (Linux):**
```bash
sudo usermod -aG docker $USER
# Log out and back in
```

### Container won't build

**Check:**
1. Dockerfile syntax is valid
2. Base image exists
3. All COPY source files exist

**Debug:**
```bash
cd <task-folder>
docker build -t test . 2>&1 | tail -50
```

### Container starts but commands fail

**Enter interactive mode to debug:**
```bash
stb harbor tasks start-env -p <task-folder> -i
```

Then run commands manually to find the issue.

---

## CI / Check Issues

### Checks pass locally but fail in PR

**Common causes:**

1. **Python version mismatch**
   - Check CI logs for version used
   - Test locally with same version

2. **Missing dependency**
   - Ensure all imports are in requirements

3. **Path differences**
   - Use absolute paths everywhere

4. **Environment variables**
   - Don't rely on local env vars

### "pinned_dependencies" failure

**Fix:** Add exact versions to all pip (or npm, etc.) installs. Make sure every Docker base image (and any pulled `image:` lines in `docker-compose.yaml`) includes an immutable `@sha256:<digest>` pin.

```dockerfile
# Before
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm
RUN pip install numpy pandas

# After
FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:<digest>
RUN pip install numpy==1.26.4 pandas==2.1.0
```

### "check_task_absolute_path" failure

**Fix:** Change relative paths to absolute in `instruction.md`:

**Before:**
```markdown
Edit config/settings.json
```

**After:**
```markdown
Edit `/app/config/settings.json`
```

### "informative_test_docstrings" failure

**Fix:** Add docstrings to all test functions:
```python
def test_output_exists():
    """Verify the output file is created at /output/result.json."""
    assert Path("/output/result.json").exists()
```

---

## Agent Issues

### API key not working

**Check:**
1. Key is set correctly:
```bash
echo $OPENAI_API_KEY
```

2. Base URL is set:
```bash
echo $OPENAI_BASE_URL
# Should be: https://api.portkey.ai/v1
```

3. Key hasn't expired (contact Slack if needed)

### Agent times out

**Possible causes:**
- Task timeout too short (increase in task.toml)
- Solution is inefficient
- Environment is slow to start
- Task is too complicated

**Fix:**
```toml
# In task.toml
[agent]
timeout_sec = 1200.0  # Increase from default
```

### Agent passes too often 

**Your task is too easy.** Make it harder by:
- Adding more steps
- Using niche knowledge
- Creating debugging scenarios
- Adding edge cases

---

## Platform Issues

### Can't log in

1. Clear browser cache and cookies
2. Try incognito/private mode
3. Verify email address is correct
4. Try different browser
5. Contact Slack if still failing

### Upload fails

1. Check file size (< 100MB)
2. Ensure ZIP structure is correct
3. Try a different browser
4. Check internet connection

### Session expires frequently

1. Enable "Remember me" on login
2. Check browser isn't blocking cookies
3. Disable interfering extensions

---

## Getting Help

### Before asking:

1. ✅ Read the error message carefully
2. ✅ Search this documentation (⌘K)
3. ✅ Check Slack for similar issues
4. ✅ Try the suggested fix

### When asking:

Include:
- What you're trying to do
- What's happening instead
- Full error message
- What you've already tried

**Bad:**
> "It's not working"

**Good:**
> "When I run `stb harbor run -a oracle`, I get `FileNotFoundError: /app/data/input.csv`. The file exists in my task folder and is included in the Dockerfile COPY command. Full error: [paste]"

### Where to ask:

- **Slack:** `#ec-terminus-submission`
- **Payment issues:** Reach out to Snorkel
