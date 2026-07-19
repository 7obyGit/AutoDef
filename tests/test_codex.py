from pathlib import Path
from unittest.mock import patch

from autodef import TaskResult, task
from autodef.services.codex import CodexService


def test_codex_service_parses_json_events(tmp_path: Path) -> None:
    stdout = '\n'.join(
        [
            '{"type":"thread.started","thread_id":"thread-1"}',
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}',
        ]
    )
    completed = type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": 0})()

    with (
        patch.object(CodexService, "available", True),
        patch("autodef.services.codex.subprocess.run", return_value=completed) as run,
    ):
        result = CodexService().run("do it", cwd=tmp_path)

    assert result == TaskResult("done", result.events, 0, "thread-1")
    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[:6] == ["codex", "exec", "--json", "--ephemeral", "--sandbox", "read-only"]
    assert "-C" in command


def test_task_decorator_returns_codex_result() -> None:
    @task
    def inspect_project(request: str) -> TaskResult:
        """Inspect the project and report the result."""
        raise AssertionError("The decorated function body must not execute")

    expected = TaskResult("complete", (), 0, "thread-1")
    with patch("autodef.decorators.task._default_service.run_task", return_value=expected) as run:
        result = inspect_project("find risks")

    assert result is expected
    run.assert_called_once()
    instruction = run.call_args.args[0]
    assert "Inspect the project" in instruction
    assert "find risks" in instruction
