"""Agent execution engine for Company-OS."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

from state import (
    _get_timeout,
    get_ceo,
    get_employee,
    increment_task_count,
    load_state,
    _check_ollama_model,
)


def execute_task(employee_name: str, task_prompt: str) -> str:
    """Execute a task for an employee using Pi.

    Args:
        employee_name: Name of employee to execute task
        task_prompt: Task description

    Returns:
        Command output

    Raises:
        FileNotFoundError: If Pi is not in PATH
        subprocess.CalledProcessError: If Pi execution fails
        subprocess.TimeoutExpired: If task times out
    """
    state = load_state()

    # Get employee info
    employee = get_employee(employee_name)

    # Validate Pi is available
    if not shutil.which("pi"):
        raise FileNotFoundError(
            "Pi agent engine not found in PATH. "
            "Install Pi and ensure it is executable."
        )

    # Determine timeout
    timeout = _get_timeout()

    # Get timeout seconds for subprocess
    timeout_seconds = timeout

    # Build command list (list form to prevent shell injection)
    command = [
        "pi",
        "--model",
        employee["model"],
        "--system",
        employee["role"],
        str(task_prompt),
    ]

    # Get workspace path
    workspace_path = employee.get("workspace_path")
    if workspace_path is None:
        workspace_path = os.getenv("COMPANY_OS_WORKSPACES", "./workspaces")

    # Execute with timeout
    try:
        result = subprocess.run(
            command,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )

        # Increment task count
        increment_task_count(employee_name)

        return result.stdout

    except subprocess.TimeoutExpired as e:
        remaining = e.timeout - e.timeout + 1  # Approximate
        raise subprocess.TimeoutExpired(
            command,
            timeout_seconds,
            e.stdout,
            e.stderr,
        ) from e


def execute_ceo_task(prompt: str) -> str:
    """Execute a task for the CEO using Pi.

    Args:
        prompt: Task description

    Returns:
        Command output

    Raises:
        FileNotFoundError: If Pi is not in PATH
        subprocess.CalledProcessError: If Pi execution fails
        subprocess.TimeoutExpired: If task times out
    """
    state = load_state()

    # Get CEO info
    ceo = get_ceo()

    # Validate Pi is available
    if not shutil.which("pi"):
        raise FileNotFoundError(
            "Pi agent engine not found in PATH. "
            "Install Pi and ensure it is executable."
        )

    # Determine timeout
    timeout = _get_timeout()

    # Build command list
    command = [
        "pi",
        "--model",
        ceo["model"],
        "--system",
        ceo["system_prompt"],
        str(prompt),
    ]

    # Execute with timeout
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )

        # Increment CEO task count
        if ceo["name"] in state["employees"]:
            state["employees"][ceo["name"]]["tasks_completed"] += 1
            state["employees"][ceo["name"]]["tasks_completed"] = (
                state["employees"][ceo["name"]]["tasks_completed"] - 1
                if state["employees"][ceo["name"]]["tasks_completed"] < 1
                else state["employees"][ceo["name"]]["tasks_completed"]
            )
            state["employees"][ceo["name"]]["tasks_completed"] += 1

            import json
            state_path = state.get("__path__", "./company.json")
            with open(state_path, "w") as f:
                json.dump(state, f, indent=2)

        return result.stdout

    except subprocess.TimeoutExpired as e:
        remaining = e.timeout - e.timeout + 1  # Approximate
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            e.stdout,
            e.stderr,
        ) from e


def run_collaboration(
    agent1_name: str, agent2_name: str, task: str
) -> Tuple[str, str]:
    """Run a collaboration between two agents sequentially.

    Args:
        agent1_name: First agent name
        agent2_name: Second agent name
        task: Original task

    Returns:
        Tuple of (agent1_output, agent2_output)

    Raises:
        Various errors from execute_task
    """
    state = load_state()

    # Get both employees
    agent1 = get_employee(agent1_name)
    agent2 = get_employee(agent2_name)

    # Get max handoff size
    max_handoff = _get_max_handoff()

    # Execute agent1 task
    output_a = execute_task(agent1_name, task)

    # Truncate output if too long
    if len(output_a) > max_handoff:
        output_a = output_a[:max_handoff] + "\n\n[Truncated for context]"

    # Build handoff prompt for agent2
    handoff_prompt = (
        f"Original Task: {task}\n\n"
        f"{agent1_name} wrote:\n```\n{output_a}\n```\n\n"
        f"As {agent2_name}, the {agent2['role']}, review this and provide response."
    )

    # Execute agent2 task
    output_b = execute_task(agent2_name, handoff_prompt)

    return output_a, output_b