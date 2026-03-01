"""Plan lifecycle management for Company-OS."""

from state import (
    get_ceo,
    get_plan,
    load_state,
    save_state,
    create_plan,
    update_plan_content,
    add_plan_revision,
    update_plan_status,
    hire_ceo,
)


# ==================== Helpers ==========
def _build_dept_roster_summary(state: dict) -> str:
    """Build a summary of departments and employees for CEO prompts.

    Args:
        state: Company state

    Returns:
        Formatted string with department information
    """
    company = state.get("company_name", "Company")
    ceo = state.get("ceo", {})
    ceo_name = ceo.get("name", "CEO")

    sections = [f"Company: {company}", f"CEO: {ceo_name}"]

    departments = state.get("departments", {})
    if departments:
        sections.append("\nDepartments:")

        for dept_name, dept_info in sorted(departments.items()):
            head = dept_info.get("head", "None")
            dept_section = f"\n### {dept_name.title()}"

            if head and head != "None":
                dept_section += f" (Head: {head})"

            employees = [
                emp["name"]
                for emp in state.get("employees", {}).values()
                if emp.get("department") == dept_name
            ]

            if employees:
                dept_section += f"\nMembers: {', '.join(employees)}"
            else:
                dept_section += f"\nMembers: (none yet)"

            sections.append(dept_section)

    return "\n".join(sections)


# ==================== Draft and Revision ==========
DRAFT_PLAN_PROMPT = """You are the CEO of {company_name}.

The following goal has been assigned to the company:
---
{goal}
---

Your task is to create a detailed structured plan.

The company organizational structure is:
{dept_roster}

Your plan should include:
1. Executive Summary - a 1-2 sentence overview
2. Clear Objectives - bullet points for what needs to be done
3. Department Breakdown - specific tasks per department with responsible parties
4. Timeline - realistic timeframes for completion
5. Success Metrics - how to measure success for each objective

The output format should be structured Markdown.
Start with the Executive Summary, then Objectives, then Department Breakdown.

For the Department Breakdown section, create a clear task description for each department that the department head can act on.

Be specific, actionable, and prioritized."""


REVISE_PLAN_PROMPT = """You are the CEO of {company_name}.

The following plan needs revision:
---
{plan_content}
---

Owner feedback:
"{feedback}"

Please revise the plan incorporating the feedback:
1. Keep the original structure but address the feedback
2. Make updates to relevant sections
3. Provide a clear updated version of the plan

Output should be complete Markdown plan content that replaces the original."""


# ==================== Core Functions ==========

def draft_plan(goal: str) -> dict:
    """Draft a new plan using CEO agent.

    Args:
        goal: The high-level goal or objective

    Returns:
        Plan dictionary with plan details

    Raises:
        ValueError: If no CEO is hired
    """
    state = load_state()

    # Verify CEO exists
    get_ceo(state)

    # Build context
    dept_roster = _build_dept_roster_summary(state)

    # Build prompt
    prompt = DRAFT_PLAN_PROMPT.format(
        company_name=state["company_name"],
        goal=goal,
        dept_roster=dept_roster,
    )

    # Use agent_runner.execute_ceo_task here, but we'll call from our layer:
    # We'll get the content from the CLI layer which will handle the Pi invocation

    # For now, just create the plan structure
    plan = create_plan(goal, "[Plan content coming from CEO agent...]")

    # Return plan
    return get_plan(plan["id"])


def request_revision(plan_id: str, feedback: str) -> dict:
    """Request a revision to a plan using CEO agent.

    Args:
        plan_id: ID of plan to revise
        feedback: Owner feedback for revision

    Returns:
        Updated plan dictionary

    Raises:
        KeyError: If plan not found
    """
    state = load_state()

    plan = get_plan(plan_id)
    original_content = plan["content"]

    # Build prompt
    prompt = REVISE_PLAN_PROMPT.format(
        company_name=state["company_name"],
        plan_content=original_content,
        feedback=feedback,
    )

    # Get revised content from CEO
    # This is called from CLI layer with Pi invocation

    # For now, just save the revision structure
    add_plan_revision(plan_id, feedback, "[Revised content coming from CEO agent...]")

    update_plan_status(plan_id, "pending-approval")

    return get_plan(plan_id)


def approve_plan(plan_id: str) -> None:
    """Approve a plan for execution.

    Args:
        plan_id: ID of plan to approve

    Raises:
        KeyError: If plan not found
        ValueError: If plan status doesn't allow approval
    """
    state = load_state()

    plan = get_plan(plan_id)

    if plan["status"] not in ("draft", "pending-approval"):
        raise ValueError(
            f"Cannot approve plan '{plan_id}'. Current status: {plan['status']}. "
            "Plan must be in 'draft' or 'pending-approval' status."
        )

    update_plan_status(plan_id, "approved")