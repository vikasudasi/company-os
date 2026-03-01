# Company-OS Implementation TODO

Track implementation status against [system-design.md](system-design.md). Use `[ ]` for not started, `[~]` for in progress, `[x]` for done.

---

## 0. Project scaffolding

- [ ] **0.1** Create project directory and `git init`
- [ ] **0.2** Set up Python 3.11+ venv (e.g. `python3 -m venv .venv`)
- [ ] **0.3** Create `pyproject.toml` with:
  - [ ] Build system: setuptools
  - [ ] Project name `company-os`, version, `requires-python = ">=3.11"`
  - [ ] Dependencies: `typer>=0.12`, `rich>=13.0`, `requests>=2.31`
  - [ ] Entry point: `company-os = "main:app"`
- [ ] **0.4** Create empty modules: `main.py`, `state.py`, `agent_runner.py`, `plan_manager.py`, `hierarchy.py`
- [ ] **0.5** Add `.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `company.json`, `workspaces/`
- [ ] **0.6** Run `pip install -e .` and verify `company-os --help` runs (empty command list)

---

## 1. State management layer (`state.py`)

### 1.1 Company lifecycle

- [ ] **1.1.1** `init_company(name: str) -> None`
  - [ ] Creates `company.json` with `company_name`, `created_at` (ISO 8601), `ceo: null`, `departments: {}`, `employees: {}`, `plans: {}`
  - [ ] Raises error if `company.json` already exists (company already initialized)
- [ ] **1.1.2** `load_state() -> dict`
  - [ ] Reads state from path: `COMPANY_OS_STATE` env var or default `./company.json`
  - [ ] Returns parsed JSON dict
  - [ ] Raises `FileNotFoundError` with message suggesting `company-os init`
- [ ] **1.1.3** `save_state(state: dict) -> None`
  - [ ] Writes atomically (temp file + `os.replace`) to state path
  - [ ] Uses same path as `load_state` (env or default)

### 1.2 CEO management

- [ ] **1.2.1** `hire_ceo(name: str, model: str) -> None`
  - [ ] Validates no CEO exists yet (raise if already hired)
  - [ ] Calls `_check_ollama_model(model)` before saving
  - [ ] Builds CEO system prompt from company name
  - [ ] Saves CEO with `name`, `model`, `system_prompt`, `tasks_completed: 0`, `hired_at` (ISO 8601)
- [ ] **1.2.2** `get_ceo() -> dict`
  - [ ] Returns CEO dict; raises `ValueError` if no CEO hired

### 1.3 Department management

- [ ] **1.3.1** `create_department(name: str) -> None`
  - [ ] Normalizes name (e.g. lowercase) for key
  - [ ] Adds to `departments` with `head: null`, `created_at`
  - [ ] Raises if department name already exists
- [ ] **1.3.2** `list_departments() -> list[dict]`
  - [ ] Returns list of department dicts (e.g. name, head, created_at, employee names)
- [ ] **1.3.3** `set_department_head(dept_name: str, employee_name: str) -> None`
  - [ ] Validates department exists
  - [ ] Validates employee exists and belongs to that department
  - [ ] Sets `departments[dept]["head"] = employee_name`
  - [ ] Sets `employees[employee_name]["is_department_head"] = true`
  - [ ] Clears previous head’s `is_department_head` if reassigning

### 1.4 Employee management

- [ ] **1.4.1** Resolve company workspace root: default `./workspaces` or `COMPANY_OS_WORKSPACES` env var
- [ ] **1.4.2** `hire_employee(name: str, role: str, model: str, department: str, workspace_path: str = None) -> None`
  - [ ] Validates employee name not already in `employees`
  - [ ] Validates department exists
  - [ ] Calls `_check_ollama_model(model)`
  - [ ] If `workspace_path` omitted: set to `<workspace_root>/<name>/` (normalized)
  - [ ] Provisions workspace: create directory and `input/`, `output/` subdirs (and optionally `plans/` placeholder)
  - [ ] Saves employee: `role`, `model`, `department`, `workspace_path`, `is_department_head: false`, `tasks_completed: 0`, `hired_at`
- [ ] **1.4.3** `fire_employee(name: str) -> None`
  - [ ] Removes employee from `employees`
  - [ ] If they were a department head, clears `departments[dept]["head"]` for that dept
- [ ] **1.4.4** `get_employee(name: str) -> dict`
  - [ ] Returns employee dict; raises `KeyError` if not found
- [ ] **1.4.5** `list_employees(department: str = None) -> list[dict]`
  - [ ] Returns all employees or filtered by department
- [ ] **1.4.6** `increment_task_count(name: str) -> None`
  - [ ] Loads state, increments `employees[name]["tasks_completed"]`, saves

### 1.5 Ollama model check

- [ ] **1.5.1** `_check_ollama_model(model: str) -> None`
  - [ ] GET `http://localhost:11434/api/tags`
  - [ ] Parses JSON for `models[].name` (or equivalent)
  - [ ] Raises `ValueError` with message like `"Model 'X' not found. Run: ollama pull X"` if not found
  - [ ] Handles `requests.ConnectionError` when Ollama not running (clear error message)

### 1.6 Plan state (CRUD)

- [ ] **1.6.1** `create_plan(goal: str, content: str) -> str`
  - [ ] Generates `plan_id` as `plan-NNN` (zero-padded, incrementing)
  - [ ] Saves plan with `goal`, `content`, `created_at`, `status: "draft"`, `revisions: []`, `department_tasks: {}`
  - [ ] Returns `plan_id`
- [ ] **1.6.2** `get_plan(plan_id: str) -> dict`
  - [ ] Returns plan dict; raises `KeyError` if not found
- [ ] **1.6.3** `list_plans() -> list[dict]`
  - [ ] Returns list of plan summaries (e.g. plan_id, goal, status, created_at)
- [ ] **1.6.4** `update_plan_status(plan_id: str, status: str) -> None`
- [ ] **1.6.5** `update_plan_content(plan_id: str, content: str) -> None`
- [ ] **1.6.6** `add_plan_revision(plan_id: str, feedback: str, revised_content: str) -> None`
  - [ ] Appends to `revisions` with `feedback`, `revised_at`, `content`

### 1.7 Plan task tracking (department & employee)

- [ ] **1.7.1** `set_dept_task(plan_id: str, dept: str, task: str) -> None`
  - [ ] Creates/updates `department_tasks[dept]` with `task`, `status: "pending"`, `employee_tasks: {}`
- [ ] **1.7.2** `set_employee_task(plan_id: str, dept: str, employee: str, task: str) -> None`
  - [ ] Creates employee task with `task`, `status: "pending"`, `output: null`
- [ ] **1.7.3** `update_dept_task_status(plan_id: str, dept: str, status: str) -> None`
- [ ] **1.7.4** `update_employee_task_status(plan_id: str, dept: str, employee: str, status: str) -> None`
- [ ] **1.7.5** `set_employee_task_output(plan_id: str, dept: str, employee: str, output: str) -> None`
- [ ] **1.7.6** `set_dept_report(plan_id: str, dept: str, report: str) -> None`
- [ ] **1.7.7** `set_ceo_report(plan_id: str, report: str) -> None`

---

## 2. CLI interface — setup commands (`main.py`)

### 2.1 App and console

- [ ] **2.1.1** Create Typer app with help text: "Company-OS: Your autonomous AI-powered company simulator."
- [ ] **2.1.2** Create `rich.console.Console()` for formatted output

### 2.2 Company setup commands

- [ ] **2.2.1** `company-os init <name>`
  - [ ] Calls `state.init_company(name)`
  - [ ] Prints success panel: "Company '<name>' initialized."
- [ ] **2.2.2** `company-os hire-ceo --name <n> --model <m>`
  - [ ] Spinner: "Verifying model with Ollama..."
  - [ ] Calls `state.hire_ceo(name, model)`
  - [ ] Prints: "CEO '<name>' appointed using model '<model>'."
- [ ] **2.2.3** `company-os create-dept --name <n>`
  - [ ] Calls `state.create_department(name)`
  - [ ] Prints: "Department '<name>' created."
- [ ] **2.2.4** `company-os hire --name <n> --role <r> --model <m> --dept <d>` (optional: `--workspace <path>`)
  - [ ] Spinner for model verification
  - [ ] Calls `state.hire_employee(...)`
  - [ ] Prints confirmation with hire details (name, role, dept, workspace_path)
- [ ] **2.2.5** `company-os set-dept-head --dept <d> --employee <n>`
  - [ ] Calls `state.set_department_head(dept, employee)`
  - [ ] Prints: "'<employee>' is now the head of the <dept> department."
- [ ] **2.2.6** `company-os roster`
  - [ ] Uses `state.get_ceo()`, `state.list_departments()`, `state.list_employees()`
  - [ ] Renders Rich tree: company name → CEO (name, model) → departments → employees (role, model; mark dept head with * or similar)
  - [ ] Handles no CEO / no departments with helpful next-step messages
- [ ] **2.2.7** `company-os fire <name>`
  - [ ] Confirmation prompt (e.g. `typer.confirm("Fire <name>? [y/N]")`)
  - [ ] Calls `state.fire_employee(name)`
  - [ ] Prints farewell message

### 2.3 CLI behaviors (global)

- [ ] **2.3.1** Input validation: reject missing or malformed args before calling state/other layers
- [ ] **2.3.2** Use `rich.progress` spinners for LLM/agent operations (e.g. "Maxwell (CEO) is thinking...")
- [ ] **2.3.3** Use `rich.markdown`, `rich.panel`, `rich.tree`, `rich.table` for output
- [ ] **2.3.4** Clear, actionable error messages with next-step suggestions

---

## 3. Execution engine (`agent_runner.py`)

### 3.1 Core execution

- [ ] **3.1.1** Resolve timeout: `COMPANY_OS_TIMEOUT` env (default 120 seconds)
- [ ] **3.1.2** `execute_task(employee_name: str, task_prompt: str) -> str`
  - [ ] Load employee via `state.get_employee(employee_name)`
  - [ ] Resolve workspace path; use as `cwd` for subprocess (sandbox)
  - [ ] Optionally inject into task prompt/context: paths to `input/` and `output/` in workspace
  - [ ] Check `shutil.which("pi")`; raise clear error if Pi not in PATH
  - [ ] Build command list: `["pi", "--model", model, "--system", role, task_prompt]` (no `shell=True`)
  - [ ] `subprocess.run(..., cwd=workspace_path, capture_output=True, text=True, timeout=timeout)`
  - [ ] On non-zero exit: raise with stderr content
  - [ ] Call `state.increment_task_count(employee_name)`
  - [ ] Return stdout
- [ ] **3.1.3** `execute_ceo_task(prompt: str) -> str`
  - [ ] Load CEO via `state.get_ceo()`
  - [ ] Use CEO system_prompt and model; no workspace (CEO has no file sandbox)
  - [ ] Same Pi invocation pattern; increment CEO tasks_completed in state
  - [ ] Return stdout

### 3.2 Error handling

- [ ] **3.2.1** Pi not found: message like "Pi agent engine not found in PATH. Install Pi and ensure it is executable."
- [ ] **3.2.2** Timeout: message like "Task timed out after N seconds. Try a simpler prompt or increase COMPANY_OS_TIMEOUT."
- [ ] **3.2.3** Non-zero exit / OOM: surface Pi stderr cleanly

---

## 4. Plan manager (`plan_manager.py`)

### 4.1 Draft and revision

- [ ] **4.1.1** Implement `_build_dept_roster_summary()` (or equivalent) for CEO context
- [ ] **4.1.2** Define `DRAFT_PLAN_PROMPT` template (company name, goal, dept roster) — output format per system-design (Executive Summary, Objectives, Department Breakdown, Timeline, Success Metrics)
- [ ] **4.1.3** `draft_plan(goal: str) -> dict`
  - [ ] Get CEO and company name from state
  - [ ] Build prompt; call `agent_runner.execute_ceo_task(prompt)`
  - [ ] Call `state.create_plan(goal, content)` → plan_id
  - [ ] Return `state.get_plan(plan_id)`
- [ ] **4.1.4** Define `REVISE_PLAN_PROMPT` (original plan, owner feedback)
- [ ] **4.1.5** `request_revision(plan_id: str, feedback: str) -> dict`
  - [ ] Load plan; build revise prompt; call `execute_ceo_task`
  - [ ] `state.add_plan_revision(plan_id, feedback, revised_content)`
  - [ ] `state.update_plan_content(plan_id, revised_content)`
  - [ ] `state.update_plan_status(plan_id, "pending-approval")`
  - [ ] Return updated plan dict
- [ ] **4.1.6** `approve_plan(plan_id: str) -> None`
  - [ ] Validate plan exists and status in `("draft", "pending-approval")`
  - [ ] `state.update_plan_status(plan_id, "approved")`

### 4.2 CLI wiring (planning commands)

- [ ] **4.2.1** `company-os plan "<goal>"`
  - [ ] Spinner: "<CEO name> (CEO) is drafting a plan..."
  - [ ] Call `plan_manager.draft_plan(goal)`
  - [ ] Render plan content in Rich markdown panel; show plan_id and status
  - [ ] Print: "Review with: company-os review-plan <plan_id>"
- [ ] **4.2.2** `company-os review-plan <plan-id>`
  - [ ] Load plan; render content as Rich markdown; show status banner; show revision history if any
- [ ] **4.2.3** `company-os revise-plan <plan-id> "<feedback>"`
  - [ ] Spinner: CEO incorporating feedback
  - [ ] Call `plan_manager.request_revision(plan_id, feedback)`
  - [ ] Render revised plan; print: "Revised. Review with: company-os review-plan <plan_id>"
- [ ] **4.2.4** `company-os approve-plan <plan-id>`
  - [ ] Confirmation: "Approve plan <plan_id>? [y/N]"
  - [ ] Call `plan_manager.approve_plan(plan_id)`
  - [ ] Print: "Plan <plan_id> approved. Run: company-os execute-plan <plan_id>"

---

## 5. Hierarchy engine (`hierarchy.py`)

### 5.1 Helpers and parsing

- [ ] **5.1.1** `_build_dept_roster_summary()` — text summary of departments and members for CEO/dept head prompts
- [ ] **5.1.2** `_parse_dept_assignments(raw_output: str) -> dict[str, str]`
  - [ ] Parse CEO output for sections prefixed with "DEPT: <name>"; return `{dept_name: task_description}`
  - [ ] Resilient to malformed output; log or fallback if parse fails
- [ ] **5.1.3** `_parse_employee_assignments(raw_output: str) -> dict[str, str]`
  - [ ] Parse dept head output for "EMPLOYEE: <name>"; return `{employee_name: task_description}`

### 5.2 CEO → departments

- [ ] **5.2.1** Define CEO breakdown prompt template (company_name, plan_content, dept_roster); output format "DEPT: <name>"
- [ ] **5.2.2** `breakdown_to_departments(plan_id: str) -> dict[str, str]`
  - [ ] Load plan; build dept roster; build prompt; `agent_runner.execute_ceo_task(prompt)`
  - [ ] Parse output; for each dept call `state.set_dept_task(plan_id, dept, task)`
  - [ ] Return `{dept_name: task_description}`

### 5.3 Department head → employees

- [ ] **5.3.1** Define dept head breakdown prompt (head_name, head_role, dept_name, company_name, dept_task, employee_roster); output format "EMPLOYEE: <name>"
- [ ] **5.3.2** `breakdown_to_employees(plan_id: str, dept: str) -> dict[str, str]`
  - [ ] Load dept task; get dept head; build employee roster; build prompt; execute dept head (via agent_runner with head as “employee”)
  - [ ] Parse output; call `state.set_employee_task(plan_id, dept, employee, task)` for each
  - [ ] Return `{employee_name: task_description}`

### 5.4 Employee task execution

- [ ] **5.4.1** `execute_employee_tasks(plan_id: str, dept: str) -> None`
  - [ ] Get employees with assigned tasks for this plan in this dept
  - [ ] For each: get task from state; call `agent_runner.execute_task(employee, task)`; save output and set status completed

### 5.5 Department report

- [ ] **5.5.1** Define dept compilation prompt (head_name, head_role, dept_name, employee_outputs)
- [ ] **5.5.2** `compile_dept_report(plan_id: str, dept: str) -> str`
  - [ ] Gather all employee outputs for dept from state; build prompt; run dept head agent; `state.set_dept_report(plan_id, dept, report)`; return report

### 5.6 CEO final report

- [ ] **5.6.1** Define CEO final report prompt (company_name, dept_reports)
- [ ] **5.6.2** `compile_ceo_report(plan_id: str) -> str`
  - [ ] Gather all dept reports; build prompt; run CEO agent; `state.set_ceo_report(plan_id, report)`; update plan status to "completed"; return report

### 5.7 CLI: execute-plan, plan-status, final-report

- [ ] **5.7.1** `company-os execute-plan <plan-id>`
  - [ ] Validate plan status is "approved"; else clear error and suggest approve-plan
  - [ ] Set plan status to "executing"
  - [ ] Step 1: print "[CEO] Breaking down plan into department tasks..."; call `breakdown_to_departments(plan_id)`; show dept tasks
  - [ ] Step 2: for each department — breakdown to employees, then execute_employee_tasks, then compile_dept_report (with progress messages per step)
  - [ ] Step 3: print "[CEO] Compiling final report..."; call `compile_ceo_report(plan_id)`
  - [ ] Print: "Execution complete. View report with: company-os final-report <plan_id>"
- [ ] **5.7.2** `company-os plan-status <plan-id>`
  - [ ] Load plan; render Rich table: Department | Task | Status | Employees (done/total); per-dept breakdown: Employee | Task | Status
- [ ] **5.7.3** `company-os final-report <plan-id>`
  - [ ] Load plan; render `ceo_report` in Rich markdown panel; header "Final Report — Plan <plan_id>"; show "Reported by: <CEO> → You (Owner)"

---

## 6. Legacy / direct assignment and collaboration

### 6.1 Assign command

- [ ] **6.1.1** `company-os assign <name> <task>`
  - [ ] Spinner: "<name> is thinking..."
  - [ ] Call `agent_runner.execute_task(name, task)`
  - [ ] Render output with `rich.markdown.Markdown`
  - [ ] Print: "Task complete. <name> has completed N tasks."

### 6.2 Collaboration pipeline

- [ ] **6.2.1** `run_collaboration(agent1_name: str, agent2_name: str, task: str) -> tuple[str, str]` in `agent_runner.py`
  - [ ] Get both employees from state
  - [ ] Run `execute_task(agent1_name, task)` → output_a
  - [ ] Build handoff prompt: original task + output_a + "As <agent2 role>, review and provide response."
  - [ ] Optionally truncate output_a to `COMPANY_OS_MAX_HANDOFF` (default 8000) to avoid context overflow
  - [ ] Run `execute_task(agent2_name, handoff_prompt)` → output_b
  - [ ] Return (output_a, output_b)
- [ ] **6.2.2** `company-os collaborate <agent1> <agent2> <task>`
  - [ ] Print: "Starting collaboration: <agent1> → <agent2>"
  - [ ] Phase 1 spinner; Phase 2 spinner
  - [ ] Call `run_collaboration(agent1, agent2, task)`
  - [ ] Render two Rich panels (one per agent) with name and role labels

---

## 7. Polish and hardening

### 7.1 Error handling (main.py)

- [ ] **7.1.1** Global try/except (or per-command) with:
  - [ ] `FileNotFoundError` → "Run 'company-os init' first"
  - [ ] `KeyError` → "Not found. Check 'company-os roster'"
  - [ ] `ValueError` → show message (e.g. model not found, invalid dept)
  - [ ] `RuntimeError` → show message and suggest next steps

### 7.2 Configuration

- [ ] **7.2.1** State path: `load_state()` / `save_state()` use `COMPANY_OS_STATE` if set, else `./company.json`
- [ ] **7.2.2** Workspace root: use `COMPANY_OS_WORKSPACES` if set, else `./workspaces`
- [ ] **7.2.3** Timeout: `COMPANY_OS_TIMEOUT` (default 120) in agent_runner
- [ ] **7.2.4** Handoff truncation: `COMPANY_OS_MAX_HANDOFF` (default 8000) in run_collaboration

### 7.3 Security

- [ ] **7.3.1** All Pi invocations use list form for subprocess (never `shell=True`)
- [ ] **7.3.2** Sanitize or strip dangerous patterns (e.g. backticks, `$()`) from role, task, and feedback strings before passing to subprocess

### 7.4 Robustness

- [ ] **7.4.1** Atomic writes in `save_state()`: write to `company.json.tmp`, then `os.replace(tmp, company.json)`
- [ ] **7.4.2** execute-plan: reject non-approved plans with clear message and correct next command

### 7.5 Misc CLI

- [ ] **7.5.1** `company-os version` — print version from package metadata (e.g. `importlib.metadata.version("company-os")`)

---

## 8. Documentation and repo

- [ ] **8.1** README.md: setup (venv, pip install, ollama, pi), basic usage (init, hire-ceo, create-dept, hire, roster, plan, execute-plan, final-report), env vars (`COMPANY_OS_STATE`, `COMPANY_OS_WORKSPACES`, `COMPANY_OS_TIMEOUT`)
- [ ] **8.2** requirements.txt (or rely on pyproject.toml): pinned versions for typer, rich, requests if desired

---

## Status summary

| Section | Description | Done | Total |
|--------|-------------|------|-------|
| 0 | Project scaffolding | 0 | 6 |
| 1 | State management | 0 | 32 |
| 2 | CLI setup commands | 0 | 15 |
| 3 | Execution engine | 0 | 8 |
| 4 | Plan manager | 0 | 12 |
| 5 | Hierarchy engine | 0 | 18 |
| 6 | Assign + collaborate | 0 | 5 |
| 7 | Polish & hardening | 0 | 12 |
| 8 | Documentation | 0 | 2 |

**Total:** 0 / 108 (update counts as you check off items)
