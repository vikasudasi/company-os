"""State management for Company-OS."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuration
DEFAULT_STATE_PATH = "./company.json"
DEFAULT_WORKSPACES_PATH = "./workspaces"


def _get_state_path() -> str:
    """Get state file path from environment variable or default."""
    return os.getenv("COMPANY_OS_STATE", DEFAULT_STATE_PATH)


def _get_workspaces_path() -> str:
    """Get workspaces directory path from environment variable or default."""
    return os.getenv("COMPANY_OS_WORKSPACES", DEFAULT_WORKSPACES_PATH)


def _get_timeout() -> int:
    """Get task timeout from environment variable or default."""
    try:
        return int(os.getenv("COMPANY_OS_TIMEOUT", "120"))
    except ValueError:
        return 120


def _get_max_handoff() -> int:
    """Get max handoff context size from environment variable or default."""
    try:
        return int(os.getenv("COMPANY_OS_MAX_HANDOFF", "8000"))
    except ValueError:
        return 8000


def _check_ollama_model(model: str) -> None:
    """Check if the specified Ollama model is available."""
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            if model not in model_names:
                raise ValueError(
                    f"Model '{model}' not found. Run: ollama pull {model}"
                )
    except requests.ConnectionError as e:
        raise ValueError(
            "Ollama is not running. Please start Ollama and ensure the model is installed."
        ) from e


def init_company(name: str) -> None:
    """Initialize company and create company.json.

    Args:
        name: Company name

    Raises:
        FileExistsError: If company.json already exists
    """
    state_path = _get_state_path()
    if os.path.exists(state_path):
        raise FileExistsError(
            f"Company already initialized at {state_path}. "
            "Run 'company-os init' again to recreate it."
        )

    state = {
        "company_name": name,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ceo": None,
        "departments": {},
        "employees": {},
        "plans": {},
    }

    save_state(state)


def load_state() -> Dict[str, Any]:
    """Load state from JSON file.

    Returns:
        Dictionary containing company state

    Raises:
        FileNotFoundError: If company.json doesn't exist
    """
    state_path = _get_state_path()
    if not os.path.exists(state_path):
        raise FileNotFoundError(
            f"Company state not initialized. Run 'company-os init' first."
        )

    with open(state_path, "r") as f:
        return json.load(f)


def save_state(state: Dict[str, Any]) -> None:
    """Save state to JSON file atomically.

    Args:
        state: Dictionary to save
    """
    state_path = _get_state_path()

    # Create temp file
    temp_path = f"{state_path}.tmp"
    with open(temp_path, "w") as f:
        json.dump(state, f, indent=2)

    # Atomically replace
    os.replace(temp_path, state_path)


# ==================== CEO Management ====================

def hire_ceo(name: str, model: str) -> None:
    """Hire the company CEO.

    Args:
        name: CEO name
        model: Ollama model to use

    Raises:
        ValueError: If CEO already hired or model not found
    """
    state = load_state()

    if state["ceo"] is not None:
        raise ValueError(f"CEO '{name}' already hired.")

    _check_ollama_model(model)

    system_prompt = f"You are the CEO of {state['company_name']}. "
    system_prompt += "You think strategically, create structured plans, and coordinate all departments to achieve company goals."

    state["ceo"] = {
        "name": name,
        "model": model,
        "system_prompt": system_prompt,
        "tasks_completed": 0,
        "hired_at": datetime.utcnow().isoformat() + "Z",
    }

    save_state(state)


def get_ceo() -> Dict[str, Any]:
    """Get CEO information.

    Returns:
        CEO dictionary

    Raises:
        ValueError: If no CEO is hired
    """
    state = load_state()
    if state["ceo"] is None:
        raise ValueError("No CEO hired. Run 'company-os hire-ceo' first.")
    return state["ceo"]


# ==================== Department Management ====================

def create_department(name: str) -> None:
    """Create a new department.

    Args:
        name: Department name (normalized to lowercase)

    Raises:
        ValueError: If department already exists
    """
    state = load_state()

    dept_name = name.lower()

    if dept_name in state["departments"]:
        raise ValueError(f"Department '{name}' already exists.")

    state["departments"][dept_name] = {
        "head": None,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    save_state(state)


def list_departments() -> List[Dict[str, Any]]:
    """List all departments.

    Returns:
        List of department information dictionaries
    """
    state = load_state()
    dept_list = []

    for dept_name, dept_info in state["departments"].items():
        employees = [
            emp["name"]
            for emp in state["employees"].values()
            if emp["department"] == dept_name
        ]

        dept_list.append({
            "name": dept_name,
            "head": dept_info.get("head"),
            "created_at": dept_info.get("created_at"),
            "employee_count": len(employees),
            "employees": employees,
        })

    return dept_list


def set_department_head(dept_name: str, employee_name: str) -> None:
    """Set a department head.

    Args:
        dept_name: Department name
        employee_name: Name of employee to appoint as head

    Raises:
        ValueError: If department exists or employee doesn't belong to department
    """
    state = load_state()

    dept_name = dept_name.lower()
    if dept_name not in state["departments"]:
        raise ValueError(f"Department '{dept_name}' does not exist.")

    if employee_name not in state["employees"]:
        raise ValueError(f"Employee '{employee_name}' not found.")

    emp = state["employees"][employee_name]
    if emp["department"] != dept_name:
        raise ValueError(
            f"Employee '{employee_name}' is not in department '{dept_name}'."
        )

    # Clear previous head if any
    if state["departments"][dept_name]["head"] is not None:
        prev_head = state["departments"][dept_name]["head"]
        state["employees"][prev_head]["is_department_head"] = False

    # Set new head
    state["departments"][dept_name]["head"] = employee_name
    emp["is_department_head"] = True

    save_state(state)


# ==================== Employee Management ====================

def hire_employee(
    name: str,
    role: str,
    model: str,
    department: str,
    workspace_path: Optional[str] = None,
) -> None:
    """Hire an employee.

    Args:
        name: Employee name
        role: Employee role description
        model: Ollama model to use
        department: Department name
        workspace_path: Optional custom workspace path

    Raises:
        ValueError: If employee exists, department doesn't, or model not found
    """
    state = load_state()

    if name in state["employees"]:
        raise ValueError(f"Employee '{name}' already exists.")

    dept_name = department.lower()
    if dept_name not in state["departments"]:
        raise ValueError(f"Department '{department}' does not exist.")

    _check_ollama_model(model)

    if workspace_path is None:
        workspace_root = _get_workspaces_path()
        workspace_name = name.lower().replace(" ", "_")
        workspace_path = os.path.join(workspace_root, workspace_name)

    # Create workspace directories
    workspace_path = os.path.abspath(workspace_path)
    os.makedirs(workspace_path, exist_ok=True)

    workspace_input = os.path.join(workspace_path, "input")
    workspace_output = os.path.join(workspace_path, "output")
    os.makedirs(workspace_input, exist_ok=True)
    os.makedirs(workspace_output, exist_ok=True)

    state["employees"][name] = {
        "role": role,
        "model": model,
        "department": dept_name,
        "workspace_path": workspace_path,
        "is_department_head": False,
        "tasks_completed": 0,
        "hired_at": datetime.utcnow().isoformat() + "Z",
    }

    save_state(state)


def fire_employee(name: str) -> None:
    """Fire an employee.

    Args:
        name: Employee name to remove

    Raises:
        KeyError: If employee not found
    """
    state = load_state()

    if name not in state["employees"]:
        raise KeyError(f"Employee '{name}' not found.")

    # Remove from employees
    department = state["employees"][name]["department"]

    # Clear department head if they were a head
    if state["departments"][department].get("head") == name:
        state["departments"][department]["head"] = None

    # Mark not a department head
    state["employees"][name]["is_department_head"] = False

    del state["employees"][name]

    save_state(state)


def get_employee(name: str) -> Dict[str, Any]:
    """Get employee information.

    Args:
        name: Employee name

    Returns:
        Employee dictionary

    Raises:
        KeyError: If employee not found
    """
    state = load_state()
    if name not in state["employees"]:
        raise KeyError(f"Employee '{name}' not found.")
    return state["employees"][name]


def list_employees(department: Optional[str] = None) -> List[Dict[str, Any]]:
    """List employees.

    Args:
        department: Optional department name to filter by

    Returns:
        List of employee information dictionaries
    """
    state = load_state()

    employees = []
    for emp_name, emp_info in state["employees"].items():
        if department is None or emp_info["department"] == department.lower():
            employees.append({
                "name": emp_name,
                "role": emp_info["role"],
                "model": emp_info["model"],
                "department": emp_info["department"],
                "is_department_head": emp_info["is_department_head"],
                "tasks_completed": emp_info["tasks_completed"],
                "hired_at": emp_info["hired_at"],
            })

    return employees


def increment_task_count(name: str) -> None:
    """Increment task completion count for an employee.

    Args:
        name: Employee name
    """
    state = load_state()

    if name not in state["employees"]:
        raise KeyError(f"Employee '{name}' not found.")

    state["employees"][name]["tasks_completed"] += 1

    save_state(state)


# ==================== Plan State ====================

def _generate_plan_id() -> str:
    """Generate a unique plan ID.

    Returns:
        Plan ID string (e.g., "plan-001")
    """
    state = load_state()
    existing_ids = [
        int(pid.split("-")[1]) for pid in state["plans"].keys()
        if pid.startswith("plan-")
    ]
    next_id = max(existing_ids) + 1 if existing_ids else 1
    return f"plan-{next_id:03d}"


def create_plan(goal: str, content: str) -> str:
    """Create a new plan.

    Args:
        goal: Plan goal
        content: Plan content

    Returns:
        Plan ID
    """
    state = load_state()

    plan_id = _generate_plan_id()
    state["plans"][plan_id] = {
        "goal": goal,
        "content": content,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "draft",
        "revisions": [],
        "department_tasks": {},
    }

    save_state(state)
    return plan_id


def get_plan(plan_id: str) -> Dict[str, Any]:
    """Get plan information.

    Args:
        plan_id: Plan ID

    Returns:
        Plan dictionary

    Raises:
        KeyError: If plan not found
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")
    return state["plans"][plan_id]


def list_plans() -> List[Dict[str, Any]]:
    """List all plans.

    Returns:
        List of plan summaries
    """
    state = load_state()

    plans = []
    for plan_id, plan_info in state["plans"].items():
        plans.append({
            "id": plan_id,
            "goal": plan_info["goal"],
            "status": plan_info["status"],
            "created_at": plan_info["created_at"],
        })

    return plans


def update_plan_status(plan_id: str, status: str) -> None:
    """Update plan status.

    Args:
        plan_id: Plan ID
        status: New status

    Raises:
        KeyError: If plan not found
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    valid_statuses = ["draft", "pending-approval", "approved", "executing", "completed"]
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    state["plans"][plan_id]["status"] = status
    save_state(state)


def update_plan_content(plan_id: str, content: str) -> None:
    """Update plan content.

    Args:
        plan_id: Plan ID
        content: New content
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    state["plans"][plan_id]["content"] = content
    save_state(state)


def add_plan_revision(
    plan_id: str, feedback: str, revised_content: str
) -> None:
    """Add a revision to a plan.

    Args:
        plan_id: Plan ID
        feedback: Owner feedback
        revised_content: Revised plan content
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    revision = {
        "feedback": feedback,
        "revised_at": datetime.utcnow().isoformat() + "Z",
        "content": revised_content,
    }

    state["plans"][plan_id]["revisions"].append(revision)
    state["plans"][plan_id]["content"] = revised_content

    save_state(state)


# ==================== Plan Task Tracking ====================

def set_dept_task(plan_id: str, dept: str, task: str) -> None:
    """Set department task for a plan.

    Args:
        plan_id: Plan ID
        dept: Department name
        task: Task description
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if "department_tasks" not in state["plans"][plan_id]:
        state["plans"][plan_id]["department_tasks"] = {}

    state["plans"][plan_id]["department_tasks"][dept] = {
        "task": task,
        "status": "pending",
        "employee_tasks": {},
        "report": None,
    }

    save_state(state)


def set_employee_task(
    plan_id: str, dept: str, employee: str, task: str
) -> None:
    """Set employee task for a plan.

    Args:
        plan_id: Plan ID
        dept: Department name
        employee: Employee name
        task: Task description
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if "department_tasks" not in state["plans"][plan_id]:
        state["plans"][plan_id]["department_tasks"] = {}

    if dept not in state["plans"][plan_id]["department_tasks"]:
        state["plans"][plan_id]["department_tasks"][dept] = {
            "task": "",
            "status": "pending",
            "employee_tasks": {},
            "report": None,
        }

    state["plans"][plan_id]["department_tasks"][dept]["employee_tasks"][
        employee
    ] = {
        "task": task,
        "status": "pending",
        "output": None,
    }

    save_state(state)


def update_dept_task_status(plan_id: str, dept: str, status: str) -> None:
    """Update department task status.

    Args:
        plan_id: Plan ID
        dept: Department name
        status: Task status
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if dept not in state["plans"][plan_id]["department_tasks"]:
        raise KeyError(f"Department '{dept}' not found in plan.")

    state["plans"][plan_id]["department_tasks"][dept]["status"] = status
    save_state(state)


def update_employee_task_status(
    plan_id: str, dept: str, employee: str, status: str
) -> None:
    """Update employee task status.

    Args:
        plan_id: Plan ID
        dept: Department name
        employee: Employee name
        status: Task status
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if dept not in state["plans"][plan_id]["department_tasks"]:
        raise KeyError(f"Department '{dept}' not found in plan.")

    if employee not in state["plans"][plan_id]["department_tasks"][dept][
        "employee_tasks"
    ]:
        raise KeyError(f"Employee '{employee}' not found in plan.")

    state["plans"][plan_id]["department_tasks"][dept]["employee_tasks"][
        employee
    ]["status"] = status
    save_state(state)


def set_employee_task_output(
    plan_id: str, dept: str, employee: str, output: str
) -> None:
    """Set employee task output.

    Args:
        plan_id: Plan ID
        dept: Department name
        employee: Employee name
        output: Task output
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if dept not in state["plans"][plan_id]["department_tasks"]:
        raise KeyError(f"Department '{dept}' not found in plan.")

    if employee not in state["plans"][plan_id]["department_tasks"][dept][
        "employee_tasks"
    ]:
        raise KeyError(f"Employee '{employee}' not found in plan.")

    state["plans"][plan_id]["department_tasks"][dept]["employee_tasks"][
        employee
    ]["output"] = output
    save_state(state)


def set_dept_report(plan_id: str, dept: str, report: str) -> None:
    """Set department report.

    Args:
        plan_id: Plan ID
        dept: Department name
        report: Report content
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    if dept not in state["plans"][plan_id]["department_tasks"]:
        raise KeyError(f"Department '{dept}' not found in plan.")

    state["plans"][plan_id]["department_tasks"][dept]["report"] = report
    save_state(state)


def set_ceo_report(plan_id: str, report: str) -> None:
    """Set CEO report.

    Args:
        plan_id: Plan ID
        report: Report content
    """
    state = load_state()
    if plan_id not in state["plans"]:
        raise KeyError(f"Plan '{plan_id}' not found.")

    state["plans"][plan_id]["ceo_report"] = report
    save_state(state)