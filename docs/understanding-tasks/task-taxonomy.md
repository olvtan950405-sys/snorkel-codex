# Task Type Taxonomy (Category)

Each task must be labeled with a category from this taxonomy. The category describes the primary theme, topic, or activity in the task.

In addition, there exists another axis of categorization called subtypes, or subcategories _(in task.toml)_

**[Refer to our page on subtypes/subcategories for more information](/portal/docs/understanding-tasks/task-subtypes)**

## Categories

### system-administration

Tasks involving OS-level configuration, user management, package management, processes, or installing, configuring, and bringing up services, networks, and environments.

**Examples:**
- Configure a systemd service
- Set up user permissions
- Install and configure Nginx

---

### build-and-dependency-management

Compile code, manage dependencies, build components.

**Examples:**
- Fix a broken build configuration
- Resolve dependency conflicts
- Set up a multi-stage Docker build

---

### data-processing

> 🚫 **Currently blocked — not accepting new submissions.** The `data-processing` category is paused. Do not submit new tasks under this category until this note is removed.

Tasks that transform, parse, filter, aggregate datasets or files and directories and generate derived output.

**Examples:**
- Parse and transform CSV data
- Aggregate log files
- Filter and sort JSON datasets

---

### games

Tasks centered on game-like or simulated environments, interactive puzzles, or simulation games that run in the terminal.

**Examples:**
- Complete a VimGolf challenge
- Solve a terminal-based puzzle
- Navigate a text adventure

---

### software-engineering

> 🚫 **Currently blocked — not accepting new submissions.** The `software-engineering` category is paused. Do not submit new tasks under this category until this note is removed.

Tasks focused on developing or testing features and algorithms, fixing bugs and improving/optimizing an existing feature, implementing tests, or maintaining software projects.

**Examples:**
- Implement a caching algorithm
- Fix a race condition
- Optimize database queries

---

### machine-learning

Tasks requiring training, fine-tuning, running inference, or evaluating machine learning models, including dependency setup, running training loops, and managing data pipelines for ML tasks.

**Examples:**
- Fine-tune a model on custom data
- Debug a training pipeline
- Optimize inference performance

---

### debugging

> 🚫 **Currently blocked — not accepting new submissions.** The `debugging` category is paused. Do not submit new tasks under this category until this note is removed.

Tasks that require identifying, diagnosing, and fixing errors in scripts, codebases, or system configurations.

**Examples:**
- Find and fix a memory leak
- Debug a failing test suite
- Diagnose a production crash

---

### Security

Tasks related to cryptography, authentication, permissions, penetration-style tests, exploit, validate vulnerabilities, reverse engineering or security configuration.

**Examples:**
- Find a SQL injection vulnerability
- Configure secure TLS settings
- Reverse engineer a binary

---

### scientific-computing

Tasks using scientific libraries or workflows, such as numerical computation, simulations, or domain-specific research code.

**Examples:**
- Implement a numerical solver
- Debug a simulation
- Optimize a scientific computation

---

## Distribution Guidelines

To ensure benchmark diversity:

- **No single type** should exceed ~30% of total tasks
- **At least four types** should each represent ≥10%

## Choosing a Category

Pick the category that best describes the **primary** activity:

| If the task mainly involves... | Use category |
|--------------------------------|--------------|
| OS/server configuration | system-administration |
| Build systems, packages | build-and-dependency-management |
| ETL, file processing | data-processing *(currently blocked)* |
| Interactive challenges | games |
| Code development, testing | software-engineering *(currently blocked)* |
| ML model work | machine-learning |
| Finding/fixing bugs | debugging *(currently blocked)* |
| Security issues | security |
| Scientific code | scientific-computing |

## Domain-Specific Tasks

If your tasks are designed for a particular domain (e.g., financial services), an additional taxonomy specific to that domain can be developed. Discuss with the team on Slack.

---

## Next Steps

- [See example tasks](/portal/docs/understanding-tasks/example-tasks)
- [Learn difficulty guidelines](/portal/docs/understanding-tasks/difficulty-guidelines)
