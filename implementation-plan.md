# Implementation Plan: Company-OS CLI

## Overview

This document outlines a phased, step-by-step plan to build the Company-OS CLI from scratch. Each phase produces a working, testable increment. The goal is to always have runnable code at the end of each phase.

**Target Stack:** Python 3.11+, Typer, Rich, Requests, Ollama, Pi

---

## Phase 0: Project Scaffolding

**Goal:** Establish a clean project skeleton with all configuration in place before writing any feature code.

### Steps

**0.1 — Initialize the repository**
```bash
mkdir company-os && cd company-os
git init
python3 -m venv .venv && source .venv/bin/activate
```

**0.2 — Create `pyproject.toml`**
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "company-os"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "rich>=13.0",
    "requests>=2.31",
]

[project.scripts]
company-os = "main:app"
```

**0.3 — Install dependencies and register CLI**
```bash
pip install -e .
```

**0.4 — Create empty module files**
```bash
touch main.py state.py agent_runner.py
```

**0.5 — Add `.gitignore`**
```
.venv/
__pycache__/
*.pyc
company.json
```

**Deliverable:** `company-os --help` runs without errors and prints an empty command list.

---

## Phase 1: State Management (`state.py`)

**Goal:** Implement all JSON read/write operations and validation logic. This layer has zero UI dependencies and can be tested in isolation.

### Steps

**1.1 — Implement `init_company(name)`**
- Creates `company.json` with `company_name`, `created_at` (ISO 8601), and an empty `employees` dict
- Raises an error if `company.json` already exists

**1.2 — Implement `load_state()` and `save_state(state)`**
- `load_state()`: Opens `company.json`, parses JSON, returns dict. Raises `FileNotFoundError` with a helpful message if not initialized.
- `save_state(state)`: Atomically writes the dict back to `company.json` (write to temp file, rename)

**1.3 — Implement `hire_employee(name, role, model)`**
- Calls `load_state()`
- Validates: name not already in `employees`
- Calls `_check_ollama_model(model)` (see 1.5)
- Appends employee to state dict with `hired_at` timestamp and `tasks_completed: 0`
- Calls `save_state()`

**1.4 — Implement `fire_employee(name)`, `get_employee(name)`, `list_employees()`**
- `fire_employee`: Removes key from employees dict, saves state
- `get_employee`: Returns the employee dict or raises `KeyError` if not found
- `list_employees`: Returns list of `{name, role, model, tasks_completed}` dicts

**1.5 — Implement `_check_ollama_model(model)`**
- `GET http://localhost:11434/api/tags`
- Parse response JSON for `models[].name` list
- Raise `ValueError` if model not found, with message: `"Model '{model}' not found. Run: ollama pull {model}"`
- Handle `requests.ConnectionError` if Ollama is not running

**1.6 — Implement `increment_task_count(name)`**
- Loads state, increments `employees[name]["tasks_completed"]`, saves

**Testing Checkpoint:**
```python
# In a REPL or test script:
from state import init_company, hire_employee, list_employees
init_company("Test Corp")
hire_employee("alice", "Python Developer", "llama3:8b")
print(list_employees())  # Should show alice
```

---

## Phase 2: CLI Interface — Core Commands (`main.py`)

**Goal:** Wire up Typer commands for `init`, `hire`, `roster`, and `fire`. All commands call into `state.py` and display output with Rich.

### Steps

**2.1 — Create the Typer app**
```python
import typer
from rich.console import Console

app = typer.Typer(help="Company-OS: Your AI-powered corporate simulator.")
console = Console()
```

**2.2 — Implement `company-os init <name>`**
```python
@app.command("init")
def init(name: str = typer.Argument(..., help="Company name")):
```
- Calls `state.init_company(name)`
- Prints success panel: `"[bold green]Company '{name}' initialized.[/bold green]"`
- Catches and prints errors cleanly

**2.3 — Implement `company-os hire`**
```python
@app.command("hire")
def hire(
    name: str = typer.Option(...),
    role: str = typer.Option(...),
    model: str = typer.Option(...),
):
```
- Shows a spinner: `"Verifying model with Ollama..."`
- Calls `state.hire_employee(name, role, model)`
- Prints confirmation table row with the new hire's details

**2.4 — Implement `company-os roster`**
- Calls `state.list_employees()`
- Renders a `rich.table.Table` with columns: `Name | Role | Model | Tasks Completed | Hired At`
- If no employees: prints `"No employees hired yet. Use 'company-os hire' to get started."`

**2.5 — Implement `company-os fire <name>`**
- Asks for confirmation: `"Fire alice? [y/N]"` using `typer.confirm`
- Calls `state.fire_employee(name)`
- Prints farewell message

**Testing Checkpoint:**
```bash
company-os init "Nexus Dynamics"
company-os hire --name alice --role "Senior Python Dev" --model llama3:8b
company-os roster
company-os fire alice
```

---

## Phase 3: Execution Engine (`agent_runner.py`)

**Goal:** Implement the subprocess-based Pi invocation and output capture.

### Steps

**3.1 — Implement `execute_task(employee_name, task_prompt) -> str`**

```python
import subprocess
import shutil

def execute_task(employee_name: str, task_prompt: str) -> str:
    employee = state.get_employee(employee_name)
    ...
```

- Verify `pi` binary is in PATH using `shutil.which("pi")`; raise `RuntimeError` if not found
- Construct command list:
  ```python
  cmd = ["pi", "--model", employee["model"], "--system", employee["role"], task_prompt]
  ```
- Run with `subprocess.run(cmd, capture_output=True, text=True, timeout=120)`
- Check `result.returncode`; raise on non-zero with stderr contents
- Call `state.increment_task_count(employee_name)`
- Return `result.stdout`

**3.2 — Implement `company-os assign <name> <task>` in `main.py`**

```python
@app.command("assign")
def assign(
    name: str = typer.Argument(...),
    task: str = typer.Argument(...),
):
```
- Show spinner: `"[name] is thinking..."`
- Call `agent_runner.execute_task(name, task)`
- Render output with `rich.markdown.Markdown` (auto-detects code blocks)
- Show task count after completion: `"Task complete. alice has completed 13 tasks."`

**3.3 — Error handling**
- `Pi not found`: `"Pi agent engine not found in PATH. Install Pi and ensure it is executable."`
- `Timeout`: `"Task timed out after 120 seconds. Try a simpler prompt or increase timeout."`
- `OOM / crash`: Surface the stderr from Pi's process for debugging

**Testing Checkpoint:**
```bash
company-os assign alice "Write a Python function that reverses a linked list"
# Should stream Alice's Pi response in Rich-formatted output
```

---

## Phase 4: Collaboration Pipeline

**Goal:** Implement the two-agent sequential handoff via the `collaborate` command.

### Steps

**4.1 — Implement `run_collaboration(agent1_name, agent2_name, task) -> tuple[str, str]` in `agent_runner.py`**

```python
def run_collaboration(agent1_name: str, agent2_name: str, task: str) -> tuple[str, str]:
    agent1 = state.get_employee(agent1_name)
    agent2 = state.get_employee(agent2_name)

    # Phase 1
    output_a = execute_task(agent1_name, task)

    # Build handoff prompt
    handoff_prompt = (
        f"Original Task: {task}\n\n"
        f"{agent1_name.title()} ({agent1['role']}) provided the following:\n\n"
        f"{output_a}\n\n"
        f"As the {agent2['role']}, review the above and provide your response."
    )

    # Phase 2
    output_b = execute_task(agent2_name, handoff_prompt)

    return output_a, output_b
```

**4.2 — Implement `company-os collaborate <agent1> <agent2> <task>` in `main.py`**

```python
@app.command("collaborate")
def collaborate(
    agent1: str = typer.Argument(...),
    agent2: str = typer.Argument(...),
    task: str = typer.Argument(...),
):
```
- Show progress panel: `"Starting collaboration pipeline: alice → bob"`
- Phase 1 spinner: `"Phase 1: alice is working..."`
- Phase 2 spinner: `"Phase 2: bob is reviewing..."`
- Render output with a two-panel Rich layout:
  ```
  ╔══════════════════════════════╗
  ║ alice (Senior Python Dev)    ║
  ╠══════════════════════════════╣
  ║ [alice's output here]        ║
  ╚══════════════════════════════╝

  ╔══════════════════════════════╗
  ║ bob (Security Auditor)       ║
  ╠══════════════════════════════╣
  ║ [bob's audited output here]  ║
  ╚══════════════════════════════╝
  ```

**Testing Checkpoint:**
```bash
company-os collaborate alice bob "Write a Python web scraper and audit it for security issues"
```

---

## Phase 5: Polish & Hardening

**Goal:** Production-ready quality: robust error handling, edge cases, and a clean user experience.

### Steps

**5.1 — Global error handler in `main.py`**
- Wrap all command bodies in `try/except` with differentiated handling for:
  - `FileNotFoundError` → "Run 'company-os init' first"
  - `KeyError` → "Employee not found. Check 'company-os roster'"
  - `ValueError` → Print the error message directly (Ollama model check)
  - `RuntimeError` → Print the message and suggest next steps

**5.2 — State file location**
- Support `COMPANY_OS_STATE` environment variable to override the default `./company.json` path
- `load_state()` checks env var first, falls back to `./company.json`

**5.3 — Shell injection prevention**
- Ensure the Pi command is passed as a list (not a string) to `subprocess.run` — this prevents shell injection by default
- Strip any backtick or `$()` patterns from role and task inputs before passing to subprocess

**5.4 — Atomic writes for `save_state()`**
- Write to `company.json.tmp` first, then `os.replace("company.json.tmp", "company.json")` to prevent corruption on crash mid-write

**5.5 — Configurable timeout**
- Add `COMPANY_OS_TIMEOUT` env var (default: `120` seconds) read by `agent_runner.py`

**5.6 — `company-os version` command**
- Print current version from `pyproject.toml` metadata

---

## Phase 6: Testing

**Goal:** Validate all functionality with a suite of unit and integration tests.

### Test Coverage

**`test_state.py`**
- `test_init_company_creates_file()`
- `test_init_company_fails_if_already_initialized()`
- `test_hire_employee_success()`
- `test_hire_employee_duplicate_fails()`
- `test_hire_employee_missing_model_fails()` (mock Ollama response)
- `test_fire_employee_success()`
- `test_fire_nonexistent_employee_fails()`
- `test_increment_task_count()`

**`test_agent_runner.py`**
- `test_execute_task_pi_not_found()` (mock `shutil.which` returning None)
- `test_execute_task_success()` (mock subprocess)
- `test_execute_task_timeout()` (mock subprocess raising `TimeoutExpired`)
- `test_run_collaboration_builds_handoff_correctly()` (mock `execute_task`)

**`test_cli.py`** (using Typer's `CliRunner`)
- `test_init_command()`
- `test_hire_command()`
- `test_roster_command_empty()`
- `test_roster_command_with_employees()`
- `test_assign_command()`
- `test_collaborate_command()`

### Run tests
```bash
pip install pytest pytest-mock
pytest tests/ -v
```

---

## Delivery Milestones

| Phase | Milestone | Deliverable |
|---|---|---|
| 0 | Project scaffolded | `company-os --help` works |
| 1 | State layer complete | JSON CRUD + Ollama validation passes |
| 2 | Core CLI commands | `init`, `hire`, `roster`, `fire` work end-to-end |
| 3 | Execution engine | `assign` invokes Pi and streams output |
| 4 | Collaboration pipeline | `collaborate` chains two agents correctly |
| 5 | Production polish | Error handling, security, env config |
| 6 | Test suite | All unit and integration tests pass |

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Pi binary not available / API changes | Medium | Abstract Pi invocation behind `agent_runner.py`; easy to swap |
| Ollama not running at validation time | Medium | Catch `ConnectionError`; print helpful startup instructions |
| LLM output too large for handoff prompt | Low | Truncate `output_a` to a configurable max chars (e.g., 8000) before handoff |
| Concurrent writes to `company.json` | Low (v1.0 is sync) | Atomic write pattern in Phase 5 mitigates risk |
| Shell injection via task/role strings | Low | Use `subprocess` list form (not shell=True); strip dangerous patterns |
