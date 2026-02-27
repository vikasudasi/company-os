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
touch main.py state.py agent_runner.py plan_manager.py hierarchy.py
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

**Goal:** Implement all JSON read/write operations and validation logic for the full schema — company, CEO, departments, employees, and plans. This layer has zero UI dependencies and can be tested in isolation.

### Steps

**1.1 — Implement `init_company(name)`**
- Creates `company.json` with `company_name`, `created_at` (ISO 8601), empty `ceo: null`, empty `departments: {}`, empty `employees: {}`, empty `plans: {}`
- Raises an error if `company.json` already exists

**1.2 — Implement `load_state()` and `save_state(state)`**
- `load_state()`: Opens `company.json`, parses JSON, returns dict. Raises `FileNotFoundError` with a helpful message if not initialized.
- `save_state(state)`: Atomically writes the dict back to `company.json` (write to temp file, then `os.replace`)

**1.3 — Implement CEO management**
- `hire_ceo(name, model)`:
  - Validates no CEO exists yet
  - Calls `_check_ollama_model(model)`
  - Constructs CEO system prompt using company name
  - Saves CEO entry with `hired_at` and `tasks_completed: 0`
- `get_ceo()`: Returns CEO dict or raises `ValueError` if not hired

**1.4 — Implement department management**
- `create_department(name)`: Adds entry to `departments` dict with `head: null` and `created_at`; raises error if dept already exists
- `list_departments()`: Returns list of dept dicts enriched with employee names
- `set_department_head(dept_name, employee_name)`:
  - Validates dept exists
  - Validates employee exists and belongs to that dept
  - Sets `departments[dept]["head"] = employee_name` and `employees[employee_name]["is_department_head"] = true`

**1.5 — Implement employee management (extended)**
- `hire_employee(name, role, model, department)`:
  - Validates name not already in `employees`
  - Validates department exists in `departments`
  - Calls `_check_ollama_model(model)`
  - Appends employee to state with `department`, `is_department_head: false`, `hired_at`, `tasks_completed: 0`
- `fire_employee(name)`: Removes from employees dict; clears dept head if applicable
- `get_employee(name)`: Returns employee dict or raises `KeyError`
- `list_employees(department=None)`: Returns filtered or full list of employees
- `increment_task_count(name)`: Loads state, increments counter, saves

**1.6 — Implement `_check_ollama_model(model)`**
- `GET http://localhost:11434/api/tags`
- Parse response JSON for `models[].name` list
- Raise `ValueError` if model not found: `"Model '{model}' not found. Run: ollama pull {model}"`
- Handle `requests.ConnectionError` if Ollama is not running

**1.7 — Implement plan state functions**
- `create_plan(goal, content)`:
  - Auto-generates `plan_id` as `"plan-{NNN}"` (padded, incrementing)
  - Saves plan with `goal`, `content`, `created_at`, `status: "draft"`, empty `revisions`, empty `department_tasks`
  - Returns `plan_id`
- `get_plan(plan_id)`: Returns plan dict or raises `KeyError`
- `list_plans()`: Returns list of `{plan_id, goal, status, created_at}` dicts
- `update_plan_status(plan_id, status)`: Updates status field
- `update_plan_content(plan_id, content)`: Updates content field
- `add_plan_revision(plan_id, feedback, revised_content)`: Appends revision record with `feedback`, `revised_at`, `content`

**1.8 — Implement plan task tracking functions**
- `set_dept_task(plan_id, dept, task)`: Creates dept task entry with `task`, `status: "pending"`, empty `employee_tasks`
- `set_employee_task(plan_id, dept, employee, task)`: Creates employee task entry with `task`, `status: "pending"`, `output: null`
- `update_dept_task_status(plan_id, dept, status)`: Updates dept task status
- `update_employee_task_status(plan_id, dept, employee, status)`: Updates employee task status
- `set_employee_task_output(plan_id, dept, employee, output)`: Saves employee output
- `set_dept_report(plan_id, dept, report)`: Saves dept head compilation report
- `set_ceo_report(plan_id, report)`: Saves CEO final report

**Testing Checkpoint:**
```python
from state import init_company, hire_ceo, create_department, hire_employee, set_department_head
init_company("Test Corp")
hire_ceo("maxwell", "llama3:8b")
create_department("engineering")
hire_employee("alice", "Engineering Lead", "llama3:8b", "engineering")
set_department_head("engineering", "alice")
print(list_employees())          # Shows alice with is_department_head=true
print(list_departments())        # Shows engineering with head=alice
```

---

## Phase 2: CLI Interface — Setup Commands (`main.py`)

**Goal:** Wire up Typer commands for company initialization, CEO hiring, department creation, employee hiring, and roster display. All commands call into `state.py` and display output with Rich.

### Steps

**2.1 — Create the Typer app**
```python
import typer
from rich.console import Console

app = typer.Typer(help="Company-OS: Your autonomous AI-powered company simulator.")
console = Console()
```

**2.2 — Implement `company-os init <name>`**
- Calls `state.init_company(name)`
- Prints success panel: `"Company '{name}' initialized."`

**2.3 — Implement `company-os hire-ceo`**
```python
@app.command("hire-ceo")
def hire_ceo(
    name: str = typer.Option(...),
    model: str = typer.Option(...),
):
```
- Shows spinner: `"Verifying model with Ollama..."`
- Calls `state.hire_ceo(name, model)`
- Prints confirmation: `"CEO '{name}' appointed using model '{model}'."`

**2.4 — Implement `company-os create-dept`**
```python
@app.command("create-dept")
def create_dept(name: str = typer.Option(...)):
```
- Calls `state.create_department(name)`
- Prints: `"Department '{name}' created."`

**2.5 — Implement `company-os hire` (extended)**
```python
@app.command("hire")
def hire(
    name: str = typer.Option(...),
    role: str = typer.Option(...),
    model: str = typer.Option(...),
    dept: str = typer.Option(...),
):
```
- Shows spinner: `"Verifying model with Ollama..."`
- Calls `state.hire_employee(name, role, model, dept)`
- Prints confirmation with new hire details

**2.6 — Implement `company-os set-dept-head`**
```python
@app.command("set-dept-head")
def set_dept_head(
    dept: str = typer.Option(...),
    employee: str = typer.Option(...),
):
```
- Calls `state.set_department_head(dept, employee)`
- Prints: `"'{employee}' is now the head of the {dept} department."`

**2.7 — Implement `company-os roster`**
- Calls `state.get_ceo()` and `state.list_departments()` and `state.list_employees()`
- Renders a `rich.tree.Tree` org chart:
  ```
  Nexus Dynamics
  └── CEO: Maxwell  [llama3:8b]
      ├── Engineering
      │   ├── * Alice (Engineering Lead) [llama3:8b]   ← * = dept head
      │   └──   Bob   (Backend Developer) [mistral:instruct]
      └── Marketing
          └── * Dave  (Marketing Director) [llama3:8b]
  ```
- If no CEO or no departments: prints helpful next-step messages

**2.8 — Implement `company-os fire <name>`**
- Asks for confirmation: `"Fire {name}? [y/N]"` via `typer.confirm`
- Calls `state.fire_employee(name)`
- Prints farewell message

**Testing Checkpoint:**
```bash
company-os init "Nexus Dynamics"
company-os hire-ceo --name maxwell --model llama3:8b
company-os create-dept --name engineering
company-os hire --name alice --role "Engineering Lead" --model llama3:8b --dept engineering
company-os set-dept-head --dept engineering --employee alice
company-os roster
```

---

## Phase 3: Execution Engine (`agent_runner.py`)

**Goal:** Implement the subprocess-based Pi invocation and output capture for both employees and the CEO.

### Steps

**3.1 — Implement `execute_task(employee_name, task_prompt) -> str`**
```python
import subprocess, shutil

def execute_task(employee_name: str, task_prompt: str) -> str:
    employee = state.get_employee(employee_name)
    ...
```
- Verify `pi` binary is in PATH via `shutil.which("pi")`; raise `RuntimeError` if not found
- Construct command list:
  ```python
  cmd = ["pi", "--model", employee["model"], "--system", employee["role"], task_prompt]
  ```
- Run with `subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)`
- Check `result.returncode`; raise on non-zero with stderr contents
- Call `state.increment_task_count(employee_name)`
- Return `result.stdout`

**3.2 — Implement `execute_ceo_task(prompt) -> str`**
- Same flow as `execute_task` but loads CEO config via `state.get_ceo()`
- Uses `ceo["system_prompt"]` as the system role
- Increments CEO `tasks_completed`

**3.3 — Implement `company-os assign <name> <task>` in `main.py`**
- Shows spinner: `"{name} is thinking..."`
- Calls `agent_runner.execute_task(name, task)`
- Renders output with `rich.markdown.Markdown`
- Shows: `"Task complete. {name} has completed {n} tasks."`

**3.4 — Error handling**
- `Pi not found`: `"Pi agent engine not found in PATH. Install Pi and ensure it is executable."`
- `Timeout`: `"Task timed out after {n} seconds. Try a simpler prompt or increase COMPANY_OS_TIMEOUT."`
- `OOM / crash`: Surface stderr from Pi's process

**Testing Checkpoint:**
```bash
company-os assign alice "Write a Python function that reverses a linked list"
```

---

## Phase 4: Plan Manager (`plan_manager.py`)

**Goal:** Implement the CEO planning loop — drafting, revising, and approving plans — and wire up the corresponding CLI commands.

### Steps

**4.1 — Implement `draft_plan(goal) -> dict`**
```python
def draft_plan(goal: str) -> dict:
    ceo = state.get_ceo()
    company_name = state.load_state()["company_name"]
    dept_roster = _build_dept_roster_summary()
    prompt = DRAFT_PLAN_PROMPT.format(
        company_name=company_name,
        goal=goal,
        dept_roster=dept_roster,
    )
    content = agent_runner.execute_ceo_task(prompt)
    plan_id = state.create_plan(goal, content)
    return state.get_plan(plan_id)
```
- `DRAFT_PLAN_PROMPT` instructs CEO to produce the structured plan markdown format
- Returns the newly created plan dict

**4.2 — Implement `request_revision(plan_id, feedback) -> dict`**
```python
def request_revision(plan_id: str, feedback: str) -> dict:
    plan = state.get_plan(plan_id)
    prompt = REVISE_PLAN_PROMPT.format(
        original_plan=plan["content"],
        feedback=feedback,
    )
    revised_content = agent_runner.execute_ceo_task(prompt)
    state.add_plan_revision(plan_id, feedback, revised_content)
    state.update_plan_content(plan_id, revised_content)
    state.update_plan_status(plan_id, "pending-approval")
    return state.get_plan(plan_id)
```

**4.3 — Implement `approve_plan(plan_id) -> None`**
- Validates plan exists and status is `"draft"` or `"pending-approval"`
- Calls `state.update_plan_status(plan_id, "approved")`

**4.4 — Implement `company-os plan "<goal>"` in `main.py`**
```python
@app.command("plan")
def plan(goal: str = typer.Argument(...)):
```
- Shows spinner: `"Maxwell (CEO) is drafting a plan..."`
- Calls `plan_manager.draft_plan(goal)`
- Renders plan content in a Rich markdown panel with header: `"Plan {plan_id} — status: draft"`
- Prints: `"Review with: company-os review-plan {plan_id}"`

**4.5 — Implement `company-os review-plan <plan-id>`**
- Calls `state.get_plan(plan_id)`
- Renders plan content as Rich markdown with a status banner at top
- Shows revision history if any exist

**4.6 — Implement `company-os revise-plan <plan-id> "<feedback>"`**
- Shows spinner: `"Maxwell (CEO) is incorporating your feedback..."`
- Calls `plan_manager.request_revision(plan_id, feedback)`
- Renders revised plan; prints: `"Revised. Review with: company-os review-plan {plan_id}"`

**4.7 — Implement `company-os approve-plan <plan-id>`**
- Asks confirmation: `"Approve plan {plan_id}? [y/N]"`
- Calls `plan_manager.approve_plan(plan_id)`
- Prints: `"Plan {plan_id} approved. Run: company-os execute-plan {plan_id}"`

**Testing Checkpoint:**
```bash
company-os plan "Build and launch a developer documentation portal"
company-os review-plan plan-001
company-os revise-plan plan-001 "Include a section on SEO strategy"
company-os approve-plan plan-001
```

---

## Phase 5: Hierarchy Engine (`hierarchy.py`)

**Goal:** Implement the full top-down execution pipeline — from CEO breaking down an approved plan to employees completing tasks and reports bubbling back up to the Owner.

### Steps

**5.1 — Implement `breakdown_to_departments(plan_id) -> dict[str, str]`**
```python
def breakdown_to_departments(plan_id: str) -> dict[str, str]:
    plan = state.get_plan(plan_id)
    dept_roster = _build_dept_roster_summary()
    prompt = CEO_BREAKDOWN_PROMPT.format(
        company_name=...,
        plan_content=plan["content"],
        dept_roster=dept_roster,
    )
    raw_output = agent_runner.execute_ceo_task(prompt)
    dept_tasks = _parse_dept_assignments(raw_output)  # parses "DEPT: <name>" sections
    for dept, task in dept_tasks.items():
        state.set_dept_task(plan_id, dept, task)
    return dept_tasks
```

**5.2 — Implement `breakdown_to_employees(plan_id, dept) -> dict[str, str]`**
- Dept head agent reads the dept task
- Uses `DEPT_HEAD_BREAKDOWN_PROMPT` to generate per-employee sub-tasks
- Parses `"EMPLOYEE: <name>"` sections from output
- Saves employee tasks via `state.set_employee_task()`
- Returns `{employee_name: task_description}`

**5.3 — Implement `execute_employee_tasks(plan_id, dept) -> None`**
- Iterates employees in the department who have assigned tasks for this plan
- Calls `agent_runner.execute_task(employee, task)` for each
- Saves output via `state.set_employee_task_output()`
- Updates status to `"completed"` via `state.update_employee_task_status()`

**5.4 — Implement `compile_dept_report(plan_id, dept) -> str`**
- Dept head agent reads all employee outputs from the plan
- Uses `DEPT_COMPILE_PROMPT` to synthesize a dept summary
- Saves report via `state.set_dept_report()`
- Returns report string

**5.5 — Implement `compile_ceo_report(plan_id) -> str`**
- CEO agent reads all dept reports from the plan
- Uses `CEO_REPORT_PROMPT` to synthesize a final company-wide update
- Saves report via `state.set_ceo_report()`
- Updates plan status to `"completed"`
- Returns report string

**5.6 — Implement `company-os execute-plan <plan-id>` in `main.py`**
```python
@app.command("execute-plan")
def execute_plan(plan_id: str = typer.Argument(...)):
```
- Validates plan status is `"approved"`; raises clear error if not
- Sets plan status to `"executing"`
- **Step 1:** Shows `"[CEO] Breaking down plan into department tasks..."` → calls `hierarchy.breakdown_to_departments(plan_id)` → prints dept task list
- **Step 2:** For each department:
  - Shows `"[{dept}] {head} is assigning tasks to team..."` → calls `hierarchy.breakdown_to_employees(plan_id, dept)` → prints employee task list
  - For each employee: shows `"{employee} is working..."` → calls `hierarchy.execute_employee_tasks(plan_id, dept)`
  - Shows `"[{dept}] {head} is compiling department report..."` → calls `hierarchy.compile_dept_report(plan_id, dept)`
- **Step 3:** Shows `"[CEO] Compiling final report for Owner..."` → calls `hierarchy.compile_ceo_report(plan_id)`
- Prints: `"Execution complete. View report with: company-os final-report {plan_id}"`

**5.7 — Implement `company-os plan-status <plan-id>`**
- Calls `state.get_plan(plan_id)`
- Renders a Rich table: `Department | Task | Status | Employees Done/Total`
- Includes a second nested view per dept: `Employee | Task | Status`

**5.8 — Implement `company-os final-report <plan-id>`**
- Calls `state.get_plan(plan_id)` to retrieve `ceo_report`
- Renders report in a Rich markdown panel with header: `"Final Report — Plan {plan_id}"`
- Shows: `"Reported by: Maxwell (CEO) → You (Owner)"`

**Testing Checkpoint:**
```bash
company-os execute-plan plan-001
# Observe step-by-step progress output per dept and employee
company-os plan-status plan-001
company-os final-report plan-001
```

---

## Phase 6: Collaboration Pipeline

**Goal:** Implement the two-agent sequential handoff for direct ad-hoc collaboration between any two employees.

### Steps

**6.1 — Implement `run_collaboration(agent1_name, agent2_name, task) -> tuple[str, str]` in `agent_runner.py`**
```python
def run_collaboration(agent1_name: str, agent2_name: str, task: str) -> tuple[str, str]:
    agent1 = state.get_employee(agent1_name)
    agent2 = state.get_employee(agent2_name)

    output_a = execute_task(agent1_name, task)

    handoff_prompt = (
        f"Original Task: {task}\n\n"
        f"{agent1_name.title()} ({agent1['role']}) provided the following:\n\n"
        f"{output_a}\n\n"
        f"As the {agent2['role']}, review the above and provide your response."
    )

    output_b = execute_task(agent2_name, handoff_prompt)
    return output_a, output_b
```

**6.2 — Implement `company-os collaborate <agent1> <agent2> <task>` in `main.py`**
- Shows: `"Starting collaboration pipeline: {agent1} → {agent2}"`
- Phase 1 spinner: `"Phase 1: {agent1} is working..."`
- Phase 2 spinner: `"Phase 2: {agent2} is reviewing..."`
- Renders two Rich panels, one per agent, labeled with name and role

**Testing Checkpoint:**
```bash
company-os collaborate alice bob "Write a Python web scraper and audit it for security issues"
```

---

## Phase 7: Polish & Hardening

**Goal:** Production-ready quality: robust error handling, edge cases, security, and a clean user experience.

### Steps

**7.1 — Global error handler in `main.py`**
- Wrap all command bodies in `try/except` with differentiated handling:
  - `FileNotFoundError` → `"Run 'company-os init' first"`
  - `KeyError` → `"Not found. Check 'company-os roster'"`
  - `ValueError` → Print the error message directly (model check, dept missing, etc.)
  - `RuntimeError` → Print the message and suggest next steps

**7.2 — State file location**
- Support `COMPANY_OS_STATE` env var to override the default `./company.json` path
- `load_state()` checks env var first, falls back to `./company.json`

**7.3 — Shell injection prevention**
- Ensure all Pi commands are passed as a list (never `shell=True`) to `subprocess.run`
- Strip backtick and `$()` patterns from role, task, and feedback inputs before subprocess injection

**7.4 — Atomic writes for `save_state()`**
- Write to `company.json.tmp` first, then `os.replace("company.json.tmp", "company.json")` to prevent corruption on crash mid-write

**7.5 — Configurable timeout**
- `COMPANY_OS_TIMEOUT` env var (default: `120` seconds) read by `agent_runner.py`

**7.6 — Plan execution guard**
- `execute-plan` rejects plans not in `"approved"` status with a clear message and the correct next command

**7.7 — Handoff truncation**
- In `run_collaboration`, truncate `output_a` to `COMPANY_OS_MAX_HANDOFF` chars (default: 8000) before building the handoff prompt, to avoid Pi context overflow

**7.8 — `company-os version` command**
- Print current version from `pyproject.toml` metadata using `importlib.metadata`

---

## Phase 8: Testing

**Goal:** Validate all functionality with a comprehensive suite of unit and integration tests.

### Test Coverage

**`test_state.py`**
- `test_init_company_creates_file()`
- `test_init_company_fails_if_already_initialized()`
- `test_hire_ceo_success()`
- `test_hire_ceo_duplicate_fails()`
- `test_create_department_success()`
- `test_create_department_duplicate_fails()`
- `test_hire_employee_with_department()`
- `test_hire_employee_invalid_department_fails()`
- `test_hire_employee_duplicate_fails()`
- `test_hire_employee_missing_model_fails()` (mock Ollama response)
- `test_set_department_head_success()`
- `test_set_department_head_wrong_dept_fails()`
- `test_fire_employee_clears_dept_head()`
- `test_increment_task_count()`
- `test_create_plan_returns_plan_id()`
- `test_add_plan_revision_appends()`
- `test_set_dept_task_and_employee_task()`

**`test_agent_runner.py`**
- `test_execute_task_pi_not_found()` (mock `shutil.which` returning None)
- `test_execute_task_success()` (mock subprocess)
- `test_execute_task_timeout()` (mock subprocess raising `TimeoutExpired`)
- `test_execute_ceo_task_success()` (mock subprocess)
- `test_run_collaboration_builds_handoff_correctly()` (mock `execute_task`)
- `test_handoff_truncation_at_max_chars()`

**`test_plan_manager.py`**
- `test_draft_plan_creates_draft_status()` (mock `execute_ceo_task`)
- `test_request_revision_appends_revision_record()` (mock `execute_ceo_task`)
- `test_approve_plan_sets_approved_status()`
- `test_approve_plan_fails_if_not_in_approvable_state()`

**`test_hierarchy.py`**
- `test_breakdown_to_departments_parses_output()` (mock CEO agent output)
- `test_breakdown_to_employees_parses_output()` (mock dept head agent output)
- `test_execute_employee_tasks_saves_outputs()` (mock `execute_task`)
- `test_compile_dept_report_saves_report()` (mock dept head agent output)
- `test_compile_ceo_report_sets_plan_completed()` (mock CEO agent output)

**`test_cli.py`** (using Typer's `CliRunner`)
- `test_init_command()`
- `test_hire_ceo_command()`
- `test_create_dept_command()`
- `test_hire_command_with_dept()`
- `test_set_dept_head_command()`
- `test_roster_command_renders_tree()`
- `test_plan_command()` (mock plan_manager)
- `test_approve_plan_command()`
- `test_execute_plan_command()` (mock hierarchy engine)
- `test_plan_status_command()`
- `test_final_report_command()`
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
| 1 | State layer complete | JSON CRUD for company, CEO, depts, employees, plans |
| 2 | Setup CLI commands | `init`, `hire-ceo`, `create-dept`, `hire`, `set-dept-head`, `roster`, `fire` work end-to-end |
| 3 | Execution engine | `assign` invokes Pi and streams output; `execute_ceo_task` works |
| 4 | Plan manager | `plan`, `review-plan`, `revise-plan`, `approve-plan` complete planning loop |
| 5 | Hierarchy engine | `execute-plan` drives full CEO → dept → employee → report pipeline |
| 6 | Collaboration pipeline | `collaborate` chains two agents correctly |
| 7 | Production polish | Error handling, security, env config, atomic writes |
| 8 | Test suite | All unit and integration tests pass |

---

## Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Pi binary not available / API changes | Medium | Abstract Pi invocation behind `agent_runner.py`; easy to swap |
| Ollama not running at validation time | Medium | Catch `ConnectionError`; print helpful startup instructions |
| CEO agent produces malformed dept breakdown | Medium | Robust `_parse_dept_assignments()` with fallback; log raw output on parse failure |
| Dept head produces malformed employee breakdown | Medium | Same parser resilience pattern; fallback assigns full task to all employees |
| LLM output too large for handoff prompt | Low | Truncate at `COMPANY_OS_MAX_HANDOFF` chars (default 8000) |
| Concurrent writes to `company.json` | Low (v1.0 is sync) | Atomic write pattern in Phase 7 mitigates risk |
| Shell injection via task/role/feedback strings | Low | Subprocess list form (not `shell=True`); strip dangerous patterns |
| Execution interrupted mid-plan | Low | Status fields on every task allow resume logic in v2.0 |
