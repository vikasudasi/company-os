# System Design: Company-OS CLI

## 1. Overview & Objective

**Company-OS** is a terminal-native, multi-agent orchestration tool that simulates a fully autonomous corporate structure using local AI. Users bootstrap an organization with departments and specialized AI Employees, then delegate high-level goals to the CEO — who autonomously plans, assigns, and tracks work across the entire org chart before reporting outcomes back to the Owner.

The system runs entirely locally, using:
- **Pi** as the agent execution engine
- **Ollama** as the local LLM provider

### Goals
- Zero cloud dependency — all inference happens on-device via Ollama
- Hierarchical organization: Owner → CEO → Department Heads → Employees
- Structured plan lifecycle: draft → owner review & approval → department breakdown → execution → reporting
- Simple, portable state stored as a flat JSON file
- Clean CLI UX with formatted output and real-time feedback
- Extendable architecture to support async/parallel agents in v2.0

---

## 2. High-Level Architecture

The system is organized into six primary layers:

```
┌──────────────────────────────────────────────────────────────────────┐
│                         CLI Interface Layer                          │
│              (main.py — Typer + Rich, user-facing)                   │
└──────────────────────────────┬───────────────────────────────────────┘
                                │
┌──────────────────────────────▼───────────────────────────────────────┐
│                       State Management Layer                         │
│             (state.py — company.json read/write)                     │
└──────────────────────────────┬───────────────────────────────────────┘
                                │
┌──────────────────────────────▼───────────────────────────────────────┐
│                        Plan Manager Layer                            │
│         (plan_manager.py — plan lifecycle & owner approval loop)     │
└──────────────────────────────┬───────────────────────────────────────┘
                                │
┌──────────────────────────────▼───────────────────────────────────────┐
│                       Hierarchy Engine Layer                         │
│      (hierarchy.py — CEO → dept head → employee task breakdown)      │
└──────────────────────────────┬───────────────────────────────────────┘
                                │
┌──────────────────────────────▼───────────────────────────────────────┐
│                      Execution Engine Layer                          │
│           (agent_runner.py — subprocess Pi invocations)              │
└──────────────────────────────┬───────────────────────────────────────┘
                                │
┌──────────────────────────────▼───────────────────────────────────────┐
│                  Inter-Agent Communication Layer                     │
│         (collaboration pipeline — sequential context handoff)        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Organizational Structure

The company mirrors a real corporate hierarchy. The Owner (the CLI user) sits above the system and interacts only with the CEO. The CEO coordinates all departments. Each department has a designated Head who manages their team of Employees.

```
Owner  (You — the CLI user)
  │
  └──► CEO  (one per company, special agent role)
            │
            ├──► Department: Engineering
            │         ├── Head: Alice  (Engineering Lead)
            │         ├── Bob          (Backend Developer)
            │         └── Carol        (Frontend Developer)
            │
            ├──► Department: Marketing
            │         ├── Head: Dave   (Marketing Director)
            │         └── Eve          (Content Writer)
            │
            └──► Department: QA
                      ├── Head: Frank  (QA Lead)
                      └── Grace        (Test Engineer)
```

### Role Responsibilities

| Role | Responsibilities |
|---|---|
| **Owner** | Sets high-level goals, reviews and approves plans, receives final reports |
| **CEO** | Drafts plans, revises on feedback, breaks plans into dept tasks, compiles final report |
| **Department Head** | Receives dept task, breaks into employee sub-tasks, reviews outputs, reports to CEO |
| **Employee** | Executes assigned sub-task via Pi/Ollama, returns output to department head |

### Employee Workspace & File Access

Each employee has a **designated workspace folder** that serves as their sole working directory. All of their task inputs and outputs are confined to this space.

- **Designated folder:** When an employee is hired, the system assigns them a workspace path (e.g. under a company workspace root). This path is stored in state and used as the working directory for every task they run.
- **Sandbox boundary:** An employee cannot read from or write to paths outside their workspace. The execution engine runs their tasks with the workspace as the current working directory and enforces that file access stays within that tree (e.g. via working directory and, where applicable, path validation or sandboxing).
- **Folder structure:** Within their workspace, employees are expected to organize work in a consistent structure so that task inputs and outputs are easy to find and audit. The standard layout is:
  - **`input/`** — Task briefs, prompts, and any inputs provided for the employee’s work.
  - **`output/`** — Artifacts, reports, and other outputs produced by the employee.
  - Optionally **`plans/<plan-id>/input/`** and **`plans/<plan-id>/output/`** for plan-scoped tasks, so work is grouped by plan.

The execution engine creates this structure when the workspace is first provisioned and passes the paths to the agent (e.g. in the task context or system prompt) so the agent knows where to read inputs from and where to write outputs.

---

## 4. Core Components

### 4.1 CLI Interface Layer (`main.py`)

**Libraries:** `typer`, `rich`

**Responsibility:** Parses user commands, validates inputs, displays formatted output, and routes to the appropriate layer.

#### Company Setup Commands

| Command | Signature | Description |
|---|---|---|
| `init` | `company-os init <name>` | Initialize company and create `company.json` |
| `hire-ceo` | `company-os hire-ceo --name <n> --model <m>` | Appoint the company CEO |
| `create-dept` | `company-os create-dept --name <n>` | Create a new department |
| `hire` | `company-os hire --name <n> --role <r> --model <m> --dept <d>` | Hire an employee into a dept |
| `set-dept-head` | `company-os set-dept-head --dept <d> --employee <n>` | Designate a dept head |
| `roster` | `company-os roster` | Display full org chart (CEO → depts → employees) |
| `fire` | `company-os fire <name>` | Remove an employee |

#### Planning & Execution Commands

| Command | Signature | Description |
|---|---|---|
| `plan` | `company-os plan "<goal>"` | Assign a goal to the CEO; CEO drafts a plan |
| `review-plan` | `company-os review-plan <plan-id>` | Owner reads the CEO's plan |
| `approve-plan` | `company-os approve-plan <plan-id>` | Owner approves the plan for execution |
| `revise-plan` | `company-os revise-plan <plan-id> "<feedback>"` | Owner sends edit feedback; CEO revises |
| `execute-plan` | `company-os execute-plan <plan-id>` | Run the approved plan through the full org hierarchy |
| `plan-status` | `company-os plan-status <plan-id>` | Check per-department and per-employee task progress |
| `final-report` | `company-os final-report <plan-id>` | View CEO's synthesized completion report |

#### Legacy Direct-Assignment Commands (still supported)

| Command | Signature | Description |
|---|---|---|
| `assign` | `company-os assign <name> <task>` | Assign a task directly to one employee |
| `collaborate` | `company-os collaborate <a> <b> <task>` | Chain two employees sequentially |

#### Key Behaviors
- **Input Validation:** Flags missing or malformed arguments before they reach downstream layers
- **Loading Spinners:** Uses `rich.progress` to show `"Maxwell (CEO) is thinking..."` during LLM inference
- **Formatted Output:** Uses `rich.markdown`, `rich.panel`, `rich.tree`, and `rich.table` for readable terminal output
- **Error Messages:** Clear, actionable error messages with next-step suggestions

---

### 4.2 State Management Layer (`state.py`)

**Storage:** `company.json` — a flat JSON file in the working directory (or configurable via `COMPANY_OS_STATE` env var)

**Responsibility:** All CRUD operations on the company structure. Acts as the single source of truth.

#### Core Functions

```python
# Company lifecycle
init_company(name: str) -> None
load_state() -> dict
save_state(state: dict) -> None

# CEO management
hire_ceo(name: str, model: str) -> None
get_ceo() -> dict

# Department management
create_department(name: str) -> None
list_departments() -> list[dict]
set_department_head(dept_name: str, employee_name: str) -> None

# Employee management
hire_employee(name: str, role: str, model: str, department: str, workspace_path: str = None) -> None
  # If workspace_path omitted, auto-assigns under company workspace root (e.g. <workspace_root>/<name>/)
fire_employee(name: str) -> None
get_employee(name: str) -> dict
list_employees(department: str = None) -> list[dict]
increment_task_count(name: str) -> None

# Plan management
create_plan(goal: str, content: str) -> str          # returns plan_id (e.g. "plan-001")
get_plan(plan_id: str) -> dict
list_plans() -> list[dict]
update_plan_status(plan_id: str, status: str) -> None
update_plan_content(plan_id: str, content: str) -> None
add_plan_revision(plan_id: str, feedback: str, revised_content: str) -> None

# Department & employee task tracking (within a plan)
set_dept_task(plan_id: str, dept: str, task: str) -> None
set_employee_task(plan_id: str, dept: str, employee: str, task: str) -> None
update_dept_task_status(plan_id: str, dept: str, status: str) -> None
update_employee_task_status(plan_id: str, dept: str, employee: str, status: str) -> None
set_employee_task_output(plan_id: str, dept: str, employee: str, output: str) -> None
set_dept_report(plan_id: str, dept: str, report: str) -> None
set_ceo_report(plan_id: str, report: str) -> None
```

#### Validation Rules
- **No duplicate names:** Returns an error if an employee or CEO with the same name already exists
- **Department existence check:** `hire` and `set-dept-head` verify the target department exists
- **CEO uniqueness:** Only one CEO allowed per company
- **Department head eligibility:** Only an existing employee within the department can be set as head
- **Ollama model check (pre-hire):** Pings `http://localhost:11434/api/tags` before saving; fails gracefully if model not found
- **Plan status gating:** `execute-plan` rejects plans not in `approved` status
- **Workspace provisioning:** On hire, the employee’s workspace directory is created (if it does not exist) with the standard `input/` and `output/` subfolders; `workspace_path` is stored in the employee record. If no path is supplied, it is derived from the company workspace root (e.g. `./workspaces` by default, or configurable via `COMPANY_OS_WORKSPACES` env var), as `<workspace_root>/<employee_name>/`

---

### 4.3 Plan Manager (`plan_manager.py`)

**Responsibility:** Manages the CEO planning loop and the owner approval lifecycle. Each plan passes through a defined set of statuses before it is ready for execution.

#### Core Functions

```python
draft_plan(goal: str) -> dict
    # Invokes CEO agent via Pi to produce a structured plan document
    # Saves plan to state with status "draft"
    # Returns plan dict

request_revision(plan_id: str, feedback: str) -> dict
    # Invokes CEO agent with original plan + owner feedback
    # Saves revision record and updates plan content
    # Sets status to "pending-approval"
    # Returns updated plan dict

approve_plan(plan_id: str) -> None
    # Sets plan status to "approved"
    # Validates plan exists and is in "draft" or "pending-approval"
```

#### Plan Status Lifecycle

```
company-os plan "<goal>"
        │
        ▼
  CEO agent drafts plan
        │
        ▼
  status: "draft"
        │
  Owner reviews via `review-plan`
        │
        ├──► `approve-plan`  ──────────────────► status: "approved"
        │                                               │
        │                                               ▼
        └──► `revise-plan "<feedback>"` ─► CEO revises ─► status: "pending-approval"
                    │                                         │
                    └── Owner reviews again ◄─────────────────┘
                          (loop until approved)
                                │
                                ▼
                          `execute-plan` becomes available
```

#### Plan Document Format (produced by CEO agent)

```markdown
# Plan: <goal>

## Executive Summary
<1–2 sentence high-level overview>

## Objectives
- Objective 1
- Objective 2

## Department Breakdown
### Engineering
- Responsible for: <specific deliverables>

### Marketing
- Responsible for: <specific deliverables>

## Timeline
- Week 1: ...
- Week 2: ...

## Success Metrics
- Metric 1
- Metric 2
```

---

### 4.4 Hierarchy Engine (`hierarchy.py`)

**Responsibility:** Drives the full top-down execution pipeline once a plan is approved. Uses AI agents at each level to intelligently break down and delegate work, then synthesizes results bottom-up back to the Owner.

#### Core Functions

```python
breakdown_to_departments(plan_id: str) -> dict[str, str]
    # CEO agent reads approved plan
    # Outputs a per-department task assignment
    # Saves dept tasks to state; returns {dept_name: task_description}

breakdown_to_employees(plan_id: str, dept: str) -> dict[str, str]
    # Department head agent reads the dept task + employee roster
    # Outputs per-employee sub-task assignments
    # Saves employee tasks to state; returns {employee_name: task_description}

execute_employee_tasks(plan_id: str, dept: str) -> None
    # Iterates over assigned employees in the dept
    # Calls agent_runner.execute_task() for each employee
    # Saves outputs to state

compile_dept_report(plan_id: str, dept: str) -> str
    # Department head agent reads all employee outputs
    # Synthesizes a concise department-level completion report
    # Saves dept report to state; returns report string

compile_ceo_report(plan_id: str) -> str
    # CEO agent reads all department reports
    # Synthesizes final company-wide update report
    # Saves CEO report to state; returns report string
```

#### Full Execution Pipeline

```
company-os execute-plan <plan-id>
        │
        ▼
[Step 1] CEO: breakdown_to_departments()
  ├── CEO agent reads the approved plan content
  ├── Generates a specific task description per department
  └── Saves dept tasks → state (status: "pending")
        │
        ▼
[Step 2] For each department (sequential in v1.0):
  │
  ├── Dept Head: breakdown_to_employees()
  │     ├── Dept head agent reads their dept task + team roster
  │     ├── Generates a specific sub-task per employee
  │     └── Saves employee tasks → state (status: "pending")
  │
  └── For each employee (sequential):
        ├── Pi invocation: agent_runner.execute_task(employee, sub-task)
        ├── Output saved → state (status: "completed")
        └── Employee task marked complete
        │
        ▼
[Step 3] Dept Head: compile_dept_report()
  ├── Dept head agent reads all employee outputs
  ├── Synthesizes department summary
  └── Dept report saved → state
        │
        ▼
[Step 4] CEO: compile_ceo_report()
  ├── CEO agent reads all dept reports
  ├── Synthesizes final company-wide update
  └── CEO report saved → state
        │
        ▼
Owner reads final report via: company-os final-report <plan-id>
```

#### Prompt Templates (used by Hierarchy Engine)

**CEO → Department breakdown prompt:**
```
You are the CEO of {company_name}.

The following plan has been approved by the Owner:
---
{plan_content}
---

The company has these departments and their members:
{dept_roster}

Break this plan into specific, actionable task assignments — one per department.
For each department, write a clear task description that the department head can act on.
Output format: one section per department, prefixed with "DEPT: <name>".
```

**Department Head → Employee breakdown prompt:**
```
You are {head_name}, the {head_role} of the {dept_name} department at {company_name}.

Your department has been assigned the following task:
---
{dept_task}
---

Your team members are:
{employee_roster}

Break this task into specific sub-tasks — one per team member.
Output format: one section per employee, prefixed with "EMPLOYEE: <name>".
```

**Department Head → Compilation prompt:**
```
You are {head_name}, the {head_role} of the {dept_name} department.

Your team has completed their tasks. Here are their outputs:
{employee_outputs}

Write a concise department summary report covering:
1. What was accomplished
2. Key outputs or deliverables
3. Any issues or blockers encountered
```

**CEO → Final report prompt:**
```
You are the CEO of {company_name}.

All departments have completed their work. Here are their reports:
{dept_reports}

Write a final update report for the Owner covering:
1. Overall execution summary
2. Highlights from each department
3. Any outstanding risks or follow-up actions
```

---

### 4.5 Execution Engine (`agent_runner.py`)

**Mechanism:** Python `subprocess` module

**Responsibility:** Assembles the Pi invocation command from employee or CEO configuration, spawns the subprocess, and captures output. For employees, execution is scoped to the employee’s designated workspace so that file access stays within that folder.

#### Core Functions

```python
execute_task(employee_name: str, task_prompt: str) -> str
execute_ceo_task(prompt: str) -> str   # Uses CEO config instead of employee config
```

#### Execution Flow

```
1. Load agent config from state.py (employee or CEO)
2. For employees: resolve workspace_path from employee config; use as cwd for subprocess (enforces sandbox — no access outside this tree)
3. Optionally inject into task context: paths to input/ and output/ (and plan-scoped subdirs if applicable) within workspace
4. Construct Pi command:
   pi --model <model> --system "<role_prompt>" "<task_prompt>"
5. Spawn subprocess (subprocess.run) with cwd=employee workspace when executing employee tasks
6. Stream/capture stdout
7. Increment tasks_completed in state
8. Return output string to caller
```

#### Employee workspace sandbox
- The execution engine runs each employee’s Pi process with **working directory** set to that employee’s `workspace_path`. The agent should treat this as the root of its file system for the task; any file reads or writes are expected to stay under this path.
- Task inputs and outputs are organized in the workspace’s `input/` and `output/` (and optionally `plans/<plan-id>/input/`, `plans/<plan-id>/output/`) so that work is auditable and consistent across employees.

#### Error Handling
- **Pi not found:** Raise a clear error if the `pi` binary is not in PATH
- **OOM / crash:** Catch non-zero exit codes and surface stderr cleanly
- **Timeout:** Configurable via `COMPANY_OS_TIMEOUT` env var (default: 120s)

---

### 4.6 Inter-Agent Communication Layer

**Location:** Extended functionality in `agent_runner.py`, triggered by the `collaborate` command

**Responsibility:** Chains two agents sequentially. The output of Agent A becomes part of the input context for Agent B.

#### Core Function

```python
run_collaboration(agent1_name: str, agent2_name: str, task: str) -> tuple[str, str]
```

#### Data Flow

```
company-os collaborate alice bob "Write and audit a web scraper"
                 │
    ┌────────────▼─────────────┐
    │  Phase 1: Alice's Task   │
    │  Pi(alice.model, task)   │
    └────────────┬─────────────┘
                 │ alice_output
    ┌────────────▼────────────────────────────────────────────┐
    │  Handoff Prompt Construction                            │
    │  "Original Task: [task]. Alice wrote: [alice_output].  │
    │   As the [bob.role], review this and provide feedback." │
    └────────────┬────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────┐
    │  Phase 2: Bob's Review   │
    │  Pi(bob.model, handoff)  │
    └────────────┬─────────────┘
                 │ bob_output
    ┌────────────▼─────────────┐
    │  CLI renders both        │
    │  outputs labeled clearly │
    └──────────────────────────┘
```

---

## 5. Data Schema (`company.json`)

```json
{
  "company_name": "Nexus Dynamics",
  "created_at": "2026-02-27T10:00:00Z",
  "ceo": {
    "name": "maxwell",
    "model": "llama3:8b",
    "system_prompt": "You are the CEO of Nexus Dynamics. You think strategically, create structured plans, and coordinate all departments to achieve company goals.",
    "tasks_completed": 3,
    "hired_at": "2026-02-27T10:01:00Z"
  },
  "departments": {
    "engineering": {
      "head": "alice",
      "created_at": "2026-02-27T10:02:00Z"
    },
    "marketing": {
      "head": "dave",
      "created_at": "2026-02-27T10:02:00Z"
    }
  },
  "employees": {
    "alice": {
      "role": "Engineering Lead. You manage engineering projects, break down technical tasks, and review your team's work.",
      "model": "llama3:8b",
      "department": "engineering",
      "workspace_path": "workspaces/alice",
      "is_department_head": true,
      "tasks_completed": 12,
      "hired_at": "2026-02-27T10:05:00Z"
    },
    "bob": {
      "role": "Backend Developer. You write clean Python APIs and focus on reliability and performance.",
      "model": "mistral:instruct",
      "department": "engineering",
      "workspace_path": "workspaces/bob",
      "is_department_head": false,
      "tasks_completed": 5,
      "hired_at": "2026-02-27T11:00:00Z"
    },
    "dave": {
      "role": "Marketing Director. You create go-to-market strategies and coordinate content campaigns.",
      "model": "llama3:8b",
      "department": "marketing",
      "workspace_path": "workspaces/dave",
      "is_department_head": true,
      "tasks_completed": 7,
      "hired_at": "2026-02-27T10:06:00Z"
    }
  },
  "plans": {
    "plan-001": {
      "goal": "Launch v2.0 of our product by end of Q3",
      "created_at": "2026-02-27T12:00:00Z",
      "status": "approved",
      "content": "# Plan: Launch v2.0...\n\n## Executive Summary\n...",
      "revisions": [
        {
          "feedback": "Add more detail on the engineering timeline",
          "revised_at": "2026-02-27T12:30:00Z",
          "content": "# Plan: Launch v2.0 (Revised)...\n..."
        }
      ],
      "department_tasks": {
        "engineering": {
          "task": "Build and test all new v2.0 features",
          "status": "completed",
          "employee_tasks": {
            "alice": {
              "task": "Architect the v2.0 system design and review all PRs",
              "status": "completed",
              "output": "Revised system design doc attached. Reviewed 8 PRs..."
            },
            "bob": {
              "task": "Implement the new authentication module",
              "status": "completed",
              "output": "Auth module implemented with JWT refresh tokens..."
            }
          },
          "dept_report": "Engineering completed all v2.0 features on schedule. Alice led architecture, Bob delivered auth module."
        },
        "marketing": {
          "task": "Prepare launch campaign and go-to-market materials",
          "status": "completed",
          "employee_tasks": {
            "dave": {
              "task": "Create the v2.0 launch announcement and campaign strategy",
              "status": "completed",
              "output": "Launch announcement drafted. Campaign scheduled for Q3 week 12..."
            }
          },
          "dept_report": "Marketing prepared full launch campaign. Dave delivered announcement copy and strategy doc."
        }
      },
      "ceo_report": "Q3 v2.0 launch plan executed successfully. Engineering delivered on time; Marketing launch campaign is ready. No blockers outstanding."
    }
  }
}
```

### Schema Notes
- `plan_id` is auto-generated as `plan-NNN` (zero-padded incrementing integer)
- Plan `status` values: `draft` → `pending-approval` → `approved` → `executing` → `completed`
- `revisions` is an append-only array; the latest entry reflects the current content
- Employee keys and department keys are lowercase strings (enforced by state layer)
- `is_department_head` is set automatically by `set-dept-head` command
- `workspace_path` is set when the employee is hired (explicit path or auto under company workspace root). The directory is created with `input/` and `output/` subfolders; employees must keep all task inputs and outputs within this tree

---

## 6. Command Lifecycle (End-to-End)

```
# ── ORGANIZATION SETUP ──────────────────────────────────────────

company-os init "Nexus Dynamics"
  └─> Creates company.json with company_name and empty structure

company-os hire-ceo --name maxwell --model llama3:8b
  └─> Verifies model with Ollama
  └─> Saves CEO entry to company.json

company-os create-dept --name engineering
company-os create-dept --name marketing
  └─> Adds empty department entries

company-os hire --name alice --role "Engineering Lead..." --model llama3:8b --dept engineering
company-os hire --name bob   --role "Backend Developer..." --model mistral:instruct --dept engineering
company-os hire --name dave  --role "Marketing Director..." --model llama3:8b --dept marketing
  └─> Verifies model, links employee to department

company-os set-dept-head --dept engineering --employee alice
company-os set-dept-head --dept marketing   --employee dave
  └─> Sets is_department_head: true and links dept.head

company-os roster
  └─> Renders Rich tree: CEO → Departments → Employees with roles and models


# ── PLANNING LOOP ────────────────────────────────────────────────

company-os plan "Launch our new product by end of Q3"
  └─> Maxwell (CEO) drafts a structured plan via Pi
  └─> Saves plan-001 with status: "draft"
  └─> Displays plan in Rich markdown panel

company-os review-plan plan-001
  └─> Displays current plan content with status banner

company-os revise-plan plan-001 "Add more detail on the engineering timeline"
  └─> Maxwell (CEO) regenerates plan incorporating the feedback
  └─> Saves revision record; status → "pending-approval"
  └─> Displays revised plan

company-os approve-plan plan-001
  └─> Sets status → "approved"
  └─> Confirms: "Plan plan-001 approved. Run: company-os execute-plan plan-001"


# ── EXECUTION PIPELINE ───────────────────────────────────────────

company-os execute-plan plan-001
  └─> [Step 1] Maxwell (CEO) breaks plan into dept tasks
        └─> Engineering task saved
        └─> Marketing task saved
  └─> [Step 2] Alice (Eng Head) breaks dept task into employee tasks
        └─> alice task saved, bob task saved
  └─> [Step 3] Alice executes her task via Pi → output saved
  └─> [Step 4] Bob executes his task via Pi → output saved
  └─> [Step 5] Alice (Eng Head) compiles dept report from team outputs
  └─> [Step 6] Dave (Marketing Head) breaks dept task → executes → compiles report
  └─> [Step 7] Maxwell (CEO) reads all dept reports → writes final report

company-os plan-status plan-001
  └─> Renders per-dept and per-employee task status table

company-os final-report plan-001
  └─> Displays CEO's synthesized report to owner in Rich panel
```

---

## 7. Project File Structure

```
company-os/
├── main.py              # CLI entry point (Typer commands)
├── state.py             # State management (JSON CRUD for all entities)
├── agent_runner.py      # Execution engine (subprocess + Pi, CEO + employee)
├── plan_manager.py      # Plan lifecycle: draft → approval → revision loop
├── hierarchy.py         # Org breakdown: CEO → dept head → employee execution
├── company.json         # Runtime state file (gitignored)
├── workspaces/          # Company workspace root (gitignored); one subdir per employee (e.g. alice/, bob/)
│   └── <employee>/       # input/, output/, optionally plans/<plan-id>/input|output
├── pyproject.toml       # Package metadata + dependencies
├── requirements.txt     # Pinned dependencies
└── README.md            # Setup and usage guide
```

---

## 8. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typer` | `>=0.12` | CLI command framework |
| `rich` | `>=13.0` | Terminal formatting, tables, trees, panels |
| `requests` | `>=2.31` | Ollama model validation API call |
| `python` | `>=3.11` | Language runtime |

**External Tools (must be installed on host):**
- `ollama` — local LLM runner
- `pi` — agent execution engine (in PATH)

---

## 9. Environment & Constraints

| Concern | Approach |
|---|---|
| Portability | Pure Python + flat JSON; works on macOS, Linux, cloud VM |
| Concurrency (v1.0) | Synchronous — departments and employees execute sequentially |
| Concurrency (v2.0) | `asyncio` + `asyncio.subprocess` for parallel department execution |
| State location | `./company.json` by default; configurable via `COMPANY_OS_STATE` env var |
| Workspace root | `./workspaces` by default; configurable via `COMPANY_OS_WORKSPACES` env var; one subfolder per employee |
| Task timeout | 120s default; configurable via `COMPANY_OS_TIMEOUT` env var |
| Security | System prompts sanitized before subprocess injection; `subprocess` list form prevents shell injection |
| Plan gating | `execute-plan` validates plan is in `approved` status before proceeding |
| Employee workspace | Each employee has a designated folder (`workspace_path`); execution uses it as cwd so the agent cannot access paths outside it. Inputs/outputs live under `input/` and `output/` (and optionally plan-scoped subdirs) within that folder |

---

## 10. Future Considerations (v2.0+)

- **Async parallel departments:** Multiple department heads executing simultaneously via `asyncio`
- **Plan templates:** Reusable plan skeletons for common workflows (product launch, hiring sprint, etc.)
- **Persistent agent memory:** Optional context carry-over between tasks for the same agent
- **Task history log:** Append-only audit trail of every task run per employee
- **Trigger-based planning:** CEO automatically drafts plans in response to defined company events
- **Web dashboard:** Read-only browser view of org chart, plan status, and task outputs from `company.json`
- **Inter-department collaboration:** Department heads can request input from peer departments mid-execution
- **Plugin agents:** Custom agent types with extended tools (browser, file-system, code interpreter)
