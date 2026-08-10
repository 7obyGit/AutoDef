"""Delegate a repository task to the Codex CLI."""

from autodef import TaskResult, task


@task(sandbox="workspace-write")
def implement_change(request: str) -> TaskResult:
    """Implement the requested change, validate it, and report the outcome."""
    return TaskResult(output="", events=(), returncode=0)


if __name__ == "__main__":
    result = implement_change("Add validation for duplicate usernames")
    print(result.output)
