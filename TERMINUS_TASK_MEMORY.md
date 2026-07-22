# Terminus task-creation memory

This repository's `docs/` directory is the authoritative source for all Terminus Edition 2 task creation and review rules. Re-read the relevant source pages when creating or auditing a task; do not treat this file as a replacement for them. Use `references/` for structural and quality examples, and place new task packages under `tasks/`.

## Current policy overrides

- New milestone tasks are blocked. Create non-milestone tasks with `number_of_milestones = 0` unless the platform documentation later removes the block.
- The `data-processing`, `software-engineering`, and `debugging` categories are currently blocked. Do not use them while those notices remain in the docs.
- Every task must set `[environment].allow_internet = false`. Bake all runtime and verifier dependencies into the image; `tests/test.sh` must not install or download them.
- Base and compose images must be digest-pinned. The runtime must contain `tmux` and `asciinema`, stay within image-context limits, and must not expose tests, oracle material, expected outputs, credentials, or solution hints.
- `tests/test.sh` must run Python pytest and always write `/logs/verifier/reward.txt`, including on failure. Its canonical reward block is the end of the script; do not add a trailing `exit`.
- Prompts must be concise, natural, self-contained, use absolute paths where paths are mentioned, specify observable outcomes without answers or procedural hints, and must not offload prompt steps into environment documentation.
- Tasks must be novel, realistic, terminal-centric, deterministic, standalone, non-privileged, and genuinely multi-step (at least five terminal commands), with fair frontier-agent difficulty. The worst evaluated model must not exceed an 80% pass rate.
- Tests must be deterministic, behavior-focused, independent of application/oracle implementation, comprehensive for every stated requirement and edge boundary, resistant to hard-coding, and identical for oracle and agent. Do not use latency/performance thresholds.
- The oracle must solve the task from scratch by a realistic deterministic method and pass every verifier test reliably; it must not hard-code expected output or exploit the verifier.
- After creating each task, perform a full Edition 2 audit covering structure, metadata, prompt/spec consistency, environment reproducibility and isolation, oracle validity, verifier quality/coverage, anti-cheating, novelty, difficulty, and packaging hygiene. Report and fix findings before handoff.

## User-added standing rules

- None yet. Append future user rules here with the date received, while preserving the platform rules above unless the user explicitly asks to supersede a user-added rule.
