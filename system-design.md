# System Design: Company-OS CLI

## 1. Overview & Objective

**Company-OS** is a terminal-native, multi-agent orchestration tool that simulates a corporate structure using local AI. Users define an organization, onboard specialized "AI Employees" (each with a distinct system prompt and a locally-running LLM), and assign them individual or collaborative tasks.

The system runs entirely locally, using:
- **Pi** as the agent execution engine
- **Ollama** as the local LLM provider

### Goals
- Zero cloud dependency — all inference happens on-device via Ollama
- Simple, portable state stored as a flat JSON file
- Clean CLI UX with formatted output and real-time feedback
- Extendable architecture to support async/parallel agents in v2.0

---

## 2. High-Level Architecture

The system is organized into four primary layers:

```
┌──────────────────────────────────────────────────────────┐
│                    CLI Interface Layer                    │
│          (main.py — Typer + Rich, user-facing)           │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                 State Management Layer                    │
│          (state.py — company.json read/write)            │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                  Execution Engine Layer                   │
│        (agent_runner.py — subprocess Pi invocations)     │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│             Inter-Agent Communication Layer               │
│   (collaboration pipeline — sequential context handoff)  │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 CLI Interface Layer (`main.py`)

**Libraries:** `typer`, `rich`

**Responsibility:** Parses user commands, validates inputs, displays formatted output, and routes to the appropriate layer.

#### Commands

| Command | Signature | Description |
|---|---|---|
| `init` | `company-os init <name>` | Initialize company and create `company.json` |
| `hire` | `company-os hire --name <n> --role <r> --model <m>` | Onboard a new AI employee |
| `roster` | `company-os roster` | Display all employees in a formatted table |
| `assign` | `company-os assign <name> <task>` | Assign a task to one employee |
| `fire` | `company-os fire <name>` | Remove an employee |
| `collaborate` | `company-os collaborate <a> <b> <task>` | Chain two employees sequentially |

#### Key Behaviors
- **Input Validation:** Flags missing or malformed arguments before they reach downstream layers
- **Loading Spinners:** Uses `rich.progress` or `rich.spinner` to show `"Alice is thinking..."` during LLM inference
- **Formatted Output:** Uses `rich.markdown`, `rich.syntax`, and `rich.table` for readable, polished terminal output
- **Error Messages:** Clear, actionable error messages (e.g., `"Model not found. Run: ollama pull llama3"`)

---

### 3.2 State Management Layer (`state.py`)

**Storage:** `company.json` — a flat JSON file in the working directory (or `~/.company-os/`)

**Responsibility:** All CRUD operations on the company structure. Acts as the single source of truth.

#### Core Functions

```python
init_company(name: str) -> None
load_state() -> dict
save_state(state: dict) -> None
hire_employee(name: str, role: str, model: str) -> None
fire_employee(name: str) -> None
get_employee(name: str) -> dict
list_employees() -> list[dict]
increment_task_count(name: str) -> None
```

#### Validation Rules
- **No duplicate names:** Returns an error if an employee with the same name already exists
- **Employee existence check:** `assign` and `collaborate` verify the target employee(s) exist before proceeding
- **Ollama model check (pre-hire):** Before saving, `state.py` pings `http://localhost:11434/api/tags` to confirm the requested model is installed. Fails gracefully with a pull instruction if not found

---

### 3.3 Execution Engine (`agent_runner.py`)

**Mechanism:** Python `subprocess` module

**Responsibility:** Assembles the Pi invocation command from employee configuration, spawns the subprocess, and captures output.

#### Core Functions

```python
execute_task(employee_name: str, task_prompt: str) -> str
```

#### Execution Flow

```
1. Load employee config from state.py
2. Construct Pi command:
   pi --model <model> --system "<role>" "<task>"
3. Spawn subprocess (subprocess.run or Popen)
4. Stream/capture stdout
5. Increment task_count in state
6. Return output string to CLI layer
```

#### Error Handling
- **Pi not found:** Raise a clear error if the `pi` binary is not in PATH
- **OOM / crash:** Catch non-zero exit codes from subprocess and surface them cleanly
- **Timeout:** Optionally enforce a configurable timeout per task (e.g., 120s default)

---

### 3.4 Inter-Agent Communication Layer (Collaboration Pipeline)

**Location:** Extended functionality in `agent_runner.py`, triggered by `collaborate` command in `main.py`

**Responsibility:** Chains two agents sequentially. The output of Agent A becomes part of the input context for Agent B.

#### Core Functions

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
    ┌────────────▼─────────────────────────────────────────────┐
    │  Handoff Prompt Construction                             │
    │  "Original Task: [task]. Alice wrote: [alice_output].    │
    │   As the [bob.role], review this and provide feedback."  │
    └────────────┬─────────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────┐
    │  Phase 2: Bob's Review   │
    │  Pi(bob.model, handoff)  │
    └────────────┬─────────────┘
                 │ bob_output
    ┌────────────▼─────────────┐
    │  CLI renders both        │
    │  outputs side-by-side    │
    └──────────────────────────┘
```

#### Output Display
The CLI renders a clear two-panel breakdown:
- **[Alice — Senior Python Developer]** → code block with her output
- **[Bob — Security Auditor]** → annotated review or corrected code

---

## 4. Data Schema (`company.json`)

```json
{
  "company_name": "Nexus Dynamics",
  "created_at": "2026-02-27T10:00:00Z",
  "employees": {
    "alice": {
      "role": "Senior Python Architect. You specialize in system design, writing modular code, and enforcing PEP8 standards.",
      "model": "llama3:8b",
      "tasks_completed": 12,
      "hired_at": "2026-02-27T10:05:00Z"
    },
    "bob": {
      "role": "QA Engineer. You write rigorous pytest suites and focus on edge-case testing.",
      "model": "mistral:instruct",
      "tasks_completed": 5,
      "hired_at": "2026-02-27T11:00:00Z"
    }
  }
}
```

### Schema Notes
- `hired_at` timestamp added for auditing and future filtering
- `tasks_completed` is auto-incremented by the execution engine after each successful run
- Employee keys are lowercase strings (enforced by state layer)

---

## 5. Command Lifecycle

```
company-os init "Nexus Dynamics"
  └─> Creates company.json with company_name and empty employees dict

company-os hire --name alice --role "Senior Python Developer..." --model llama3:8b
  └─> Pings Ollama to verify model exists
  └─> Writes alice entry to company.json

company-os roster
  └─> Reads company.json
  └─> Renders Rich table: Name | Role | Model | Tasks Completed

company-os assign alice "Write a FastAPI server with JWT auth"
  └─> Loads alice config from state
  └─> Spawns: pi --model llama3:8b --system "<alice.role>" "<task>"
  └─> Streams output to terminal with Rich formatting
  └─> Increments alice.tasks_completed

company-os collaborate alice bob "Write a web scraper and audit it"
  └─> Runs alice's task (Phase 1)
  └─> Captures output, builds handoff prompt
  └─> Runs bob's task with handoff context (Phase 2)
  └─> Renders both outputs labeled by employee

company-os fire alice
  └─> Removes alice from company.json
```

---

## 6. Project File Structure

```
company-os/
├── main.py              # CLI entry point (Typer commands)
├── state.py             # State management (JSON CRUD)
├── agent_runner.py      # Execution engine (subprocess + Pi)
├── company.json         # Runtime state file (gitignored)
├── pyproject.toml       # Package metadata + dependencies
├── requirements.txt     # Pinned dependencies
└── README.md            # Setup and usage guide
```

---

## 7. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `typer` | `>=0.12` | CLI command framework |
| `rich` | `>=13.0` | Terminal formatting and output |
| `requests` | `>=2.31` | Ollama model validation API call |
| `python` | `>=3.11` | Language runtime |

**External Tools (must be installed on host):**
- `ollama` — local LLM runner
- `pi` — agent execution engine (in PATH)

---

## 8. Environment & Constraints

| Concern | Approach |
|---|---|
| Portability | Pure Python + flat JSON; works on macOS, Linux, cloud VM |
| Concurrency (v1.0) | Synchronous — CLI blocks until each agent finishes |
| Concurrency (v2.0) | `asyncio` + `asyncio.subprocess` for parallel agent execution |
| State location | `./company.json` by default; configurable via `COMPANY_OS_STATE` env var |
| Security | System prompts are sanitized before subprocess injection to prevent shell injection |

---

## 9. Future Considerations (v2.0+)

- **Async parallel execution:** Multiple employees working on independent tasks simultaneously
- **Task history log:** Append-only log of all tasks run per employee
- **Agent memory:** Optional context window carry-over between tasks for the same employee
- **Plugin system:** Allow custom agent types (e.g., browser agent, file-system agent)
- **Web dashboard:** Read-only HTML view of `company.json` rendered in a browser
