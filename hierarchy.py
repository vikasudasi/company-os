"""Organization hierarchy engine for Company-OS."""


# ==================== Helpers and Parsing ==========

def _build_dept_roster_summary(state: dict) -> str:
    """Build a summary of departments and employees for hierarchy prompts."""
    company = state.get("company_name", "Company")

    sections = [f"Company: {company}"]

    departments = state.get("departments", {})
    if departments:
        sections.append("\nDepartments:")

        for dept_name, dept_info in sorted(departments.items()):
            head = dept_info.get("head", "None")
            dept_section = f"\n### {dept_name.title()} (Head: {head})"

            employees = [
                emp["name"]
                for emp in state.get("employees", {}).values()
                if emp.get("department") == dept_name
            ]

            if employees:
                roster = []
                for emp in sorted(employees):
                    emp_info = state["employees"][emp]
                    roster.append(
                        f"- {emp}: {emp_info['role']}"
                    )
                dept_section += f"\nTeam:\n" + "\n".join(roster)
            else:
                dept_section += f"\nTeam: (none yet)"

            sections.append(dept_section)

    return "\n".join(sections)


def _parse_dept_assignments(raw_output: str) -> dict:
    """Parse CEO output for department assignments.

    Args:
        raw_output: Raw output from CEO agent

    Returns:
        Dictionary mapping department names to task descriptions
    """
    assignments = {}
    current_dept = None
    current_task = []

    for line in raw_output.split("\n"):
        if line.strip().startswith("DEPT:"):
            # Save previous department if exists
            if current_dept and current_task:
                assignments[current_dept] = "\n".join(current_task).strip()
                current_task = []

            # Start new department
            current_dept = line.strip()[5:].strip()  # Remove "DEPT:"
        elif current_dept is not None:
            # Collect task lines
            current_task.append(line)

    # Don't forget the last department
    if current_dept and current_task:
        assignments[current_dept] = "\n".join(current_task).strip()

    return assignments


def _parse_employee_assignments(raw_output: str) -> dict:
    """Parse department head output for employee assignments.

    Args:
        raw_output: Raw output from department head agent

    Returns:
        Dictionary mapping employee names to task descriptions
    """
    assignments = {}
    current_employee = None
    current_task = []

    for line in raw_output.split("\n"):
        if line.strip().startswith("EMPLOYEE:"):
            # Save previous employee if exists
            if current_employee and current_task:
                assignments[current_employee] = "\n".join(current_task).strip()
                current_task = []

            # Start new employee
            current_employee = line.strip()[9:].strip()  # Remove "EMPLOYEE:"
        elif current_employee is not None:
            # Collect task lines
            current_task.append(line)

    # Don't forget the last employee
    if current_employee and current_task:
        assignments[current_employee] = "\n".join(current_task).strip()

    return assignments


# ==================== Prompts ==========

CEO_DEPT_BREAKDOWN_PROMPT = """You are the CEO of {company_name}.

The following plan has been approved by the Owner:
---
{plan_content}
---

The company has these departments and their members:
{dept_roster}

Break this plan into specific, actionable task assignments — one per department.
For each department, write a clear task description that the department head can act on.

Output format: one section per department, prefixed with "DEPT: <name>".

Be specific and actionable."""


DEPT_HEAD_BREAKDOWN_PROMPT = """You are {head_name}, the {head_role} of the {dept_name} department at {company_name}.

Your department has been assigned the following task:
---
{dept_task}
---

Your team members are:
{employee_roster}

Break this task into specific sub-tasks — one per team member.
Output format: one section per employee, prefixed with "EMPLOYEE: <name>".

Be clear about what each person should do."""


DEPT_COMPILATION_PROMPT = """You are {head_name}, the {head_role} of the {dept_name} department at {company_name}.

Your team has completed their tasks. Here are their outputs:
{employee_outputs}

Write a concise department summary report covering:
1. What was accomplished
2. Key outputs or deliverables
3. Any issues or blockers encountered

Keep it brief (2-4 paragraphs) and actionable."""


CEO_FINAL_REPORT_PROMPT = """You are the CEO of {company_name}.

All departments have completed their work. Here are their reports:
{dept_reports}

Write a final update report for the Owner covering:
1. Overall execution summary
2. Highlights from each department
3. Any outstanding risks or follow-up actions

Keep it professional and strategic."""


# ==================== Core Hierarchy Functions ==========

def breakdown_to_departments(plan_id: str) -> dict:
    """Break down approved plan into department tasks.

    Args:
        plan_id: ID of approved plan

    Returns:
        Dictionary of department_name -> task_description
    """
    from agent_runner import execute_ceo_task
    from state import create_plan, get_plan, update_plan_status, save_state

    state = __import__("state").load_state()
    plan = get_plan(plan_id)

    # Build context
    dept_roster = _build_dept_roster_summary(state)
    plan_content = plan["content"]

    # Build and execute prompt
    prompt = CEO_DEPT_BREAKDOWN_PROMPT.format(
        company_name=state["company_name"],
        plan_content=plan_content,
        dept_roster=dept_roster,
    )

    output = execute_ceo_task(prompt)
    assignments = _parse_dept_assignments(output)

    # Save assignments to state
    if "department_tasks" not in plan:
        import json
        state["plans"][plan_id]["department_tasks"] = {}

    for dept, dept_task in assignments.items():
        if dept.lower() in state["plans"][plan_id]["department_tasks"]:
            continue

        create_plan = __import__("state", fromlist=["create_plan"])
        create_plan(dept, dept_task)

    # Update plan status
    update_plan_status(plan_id, "executing")

    return assignments


def breakdown_to_employees(plan_id: str, dept: str) -> dict:
    """Break down department task into employee tasks.

    Args:
        plan_id: ID of plan
        dept: Department name

    Returns:
        Dictionary of employee_name -> task_description
    """
    from agent_runner import execute_ceo_task
    from state import (
        get_employee,
        get_plan,
        hire_ceo,
        list_emplyees,
        set_employee_task,
        load_state,
    )

    state = load_state()
    plan = get_plan(plan_id)

    # Get department task
    if "department_tasks" not in plan:
        raise ValueError(f"Department tasks not initialized for plan {plan_id}")

    if dept not in plan["department_tasks"]:
        raise ValueError(f"Department '{dept}' not found in plan")

    dept_info = plan["department_tasks"][dept]
    dept_task = dept_info.get("task", "")

    if not dept_task:
        raise ValueError(f"Department '{dept}' has no task assigned")

    # Get employees in department
    employees = [
        emp["name"]
        for emp in state["employees"].values()
        if emp.get("department") == dept.lower() and not emp.get("is_department_head", False)
    ]

    if not employees:
        raise ValueError(f"Department '{dept}' has no employees")

    # Build employee roster
    employee_roster = ""
    for emp_name in employees:
        emp = get_employee(emp_name)
        employee_roster += f"- {emp_name}: {emp['role']}\n"

    # Get department head
    dept_head = None
    if state["departments"].get(dept.lower(), {}).get("head"):
        dept_head = get_employee(state["departments"][dept.lower()]["head"])

    # Build and execute prompt
    head_name = dept_head["name"] if dept_head else dept
    head_role = dept_head["role"] if dept_head else "department head"

    prompt = DEPT_HEAD_BREAKDOWN_PROMPT.format(
        head_name=head_name,
        head_role=head_role,
        dept_name=dept,
        dept_task=dept_task,
        employee_roster=employee_roster,
    )

    output = execute_ceo_task(prompt)
    assignments = _parse_employee_assignments(output)

    # Save assignments to state
    for emp, emp_task in assignments.items():
        set_employee_task(plan_id, dept, emp, emp_task)

    return assignments


def execute_employee_tasks(plan_id: str, dept: str) -> None:
    """Execute all employee tasks for a department in a plan.

    Args:
        plan_id: Plan ID
        dept: Department name
    """
    from agent_runner import execute_task
    from state import get_plan, set_employee_task_status, load_state

    state = load_state()
    plan = get_plan(plan_id)

    if "department_tasks" not in plan:
        return

    if dept not in plan["department_tasks"]:
        return

    employee_tasks = plan["department_tasks"][dept].get("employee_tasks", {})

    for emp_name, task in employee_tasks.items():
        print(f"  📋 Executing task for {emp_name}... ", end="", flush=True)
        output = execute_task(emp_name, task)
        print(f"✓")

        # Save output and mark complete
        set_employee_task_output = __import__(
            "state", fromlist=["set_employee_task_output"]
        )
        set_employee_task_output(plan_id, dept, emp_name, output)

        set_employee_task_status = __import__(
            "state", fromlist=["set_employee_task_status"]
        )
        set_employee_task_status(plan_id, dept, emp_name, "completed")

    # Mark department task as completed
    update_dept_task_status = __import__(
        "state", fromlist=["update_dept_task_status"]
    )
    update_dept_task_status(plan_id, dept, "completed")


def compile_dept_report(plan_id: str, dept: str) -> str:
    """Compile department report from employee outputs.

    Args:
        plan_id: Plan ID
        dept: Department name

    Returns:
        Department report string
    """
    from agent_runner import execute_ceo_task
    from state import (
        get_employee,
        get_plan,
        get_plan,
        hire_ceo,
        load_state,
        save_state,
        hire_ceo,
    )

    state = load_state()
    plan = get_plan(plan_id)

    if "department_tasks" not in plan:
        raise ValueError(f"Department tasks not initialized for plan {plan_id}")

    if dept not in plan["department_tasks"]:
        raise ValueError(f"Department '{dept}' not found in plan")

    # Get all employee outputs for this department
    employee_tasks = plan["department_tasks"][dept].get("employee_tasks", {})
    employee_outputs = []

    for emp_name, task_info in employee_tasks.items():
        output = task_info.get("output")
        if output:
            employee_outputs.append(f"**{emp_name}:**\n{output}")

    if not employee_outputs:
        raise ValueError(f"No outputs collected from {dept}")

    # Get department head
    dept_head_name = state["departments"].get(dept, {}).get("head")
    if not dept_head_name:
        raise ValueError(f"Department head not set for {dept}")

    dept_head = get_employee(dept_head_name)

    # Build prompt
    prompt = DEPT_COMPILATION_PROMPT.format(
        head_name=dept_head_name,
        head_role=dept_head["role"],
        dept_name=dept,
        employee_outputs="\n\n".join(employee_outputs),
    )

    # Execute and compile
    report = execute_ceo_task(prompt)

    # Save report to state
    set_dept_report = __import__("state", fromlist=["set_dept_report"])
    set_dept_report(plan_id, dept, report)

    return report


def compile_ceo_report(plan_id: str) -> str:
    """Compile final CEO report from department reports.

    Args:
        plan_id: Plan ID

    Returns:
        CEO report string
    """
    from agent_runner import execute_ceo_task
    from state import get_plan, get_plan, hire_ceo, load_state

    state = load_state()
    plan = get_plan(plan_id)

    # Get all department reports
    dept_reports = []

    if "department_tasks" in plan:
        for dept, dept_info in plan["department_tasks"].items():
            report = dept_info.get("report")
            if report:
                dept_reports.append(f"**{dept.upper()}:**\n{report}")

    if not dept_reports:
        raise ValueError("No department reports available")

    # Build prompt
    prompt = CEO_FINAL_REPORT_PROMPT.format(
        company_name=state["company_name"],
        dept_reports="\n\n".join(dept_reports),
    )

    # Execute and compile
    report = execute_ceo_task(prompt)

    # Save report to state
    hire_ceo = __import__("state", fromlist=["hire_ceo"])
    hire_ceo(plan_id, report)

    return report