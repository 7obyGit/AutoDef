from pathlib import Path
from unittest.mock import patch

import pytest

from autodef import TaskResult, task
from autodef.services.codex import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_CODEX_REASONING_EFFORT,
    CodexService,
)


def test_codex_service_parses_json_events(tmp_path: Path) -> None:
    stdout = "\n".join(
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
        result = CodexService().run("do it", cwd=tmp_path, images=[tmp_path / "input.png"])

    assert result == TaskResult("done", result.events, 0, "thread-1")
    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[:6] == [
        "codex",
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "workspace-write",
    ]
    assert "-C" in command
    assert "--image" in command
    assert str(tmp_path / "input.png") in command
    assert "--model" in command
    assert DEFAULT_CODEX_MODEL in command
    assert 'model_reasoning_effort="medium"' in command


def test_codex_defaults_to_luna_medium_without_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "empty-codex-home"))
    monkeypatch.delenv("AUTODEF_CODEX_MODEL", raising=False)
    monkeypatch.delenv("AUTODEF_CODEX_REASONING_EFFORT", raising=False)

    service = CodexService()

    assert service.model == DEFAULT_CODEX_MODEL
    assert service.reasoning_effort == DEFAULT_CODEX_REASONING_EFFORT


def test_codex_respects_configured_model_and_reasoning_effort(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        'model = "custom-model"\nmodel_reasoning_effort = "high"\n', encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("AUTODEF_CODEX_MODEL", raising=False)
    monkeypatch.delenv("AUTODEF_CODEX_REASONING_EFFORT", raising=False)

    service = CodexService()

    assert service.model == "custom-model"
    assert service.reasoning_effort == "high"


def test_codex_finds_git_root_for_implicit_cwd(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    nested = repository / "examples" / "flows"
    (repository / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)

    assert CodexService._workspace_root(nested) == repository


def test_codex_run_uses_git_root_when_called_from_nested_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repository = tmp_path / "repository"
    nested = repository / "examples" / "flows"
    (repository / ".git").mkdir(parents=True)
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    completed = type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()

    with (
        patch.object(CodexService, "available", True),
        patch("autodef.services.codex.subprocess.run", return_value=completed) as run,
    ):
        CodexService().run("do it")

    command = run.call_args.args[0]
    assert command[command.index("-C") + 1] == str(repository)
    assert run.call_args.kwargs["cwd"] == str(repository)


def test_codex_skips_repo_check_outside_git_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    completed = type("Completed", (), {"stdout": "", "stderr": "", "returncode": 0})()

    with (
        patch.object(CodexService, "available", True),
        patch("autodef.services.codex.subprocess.run", return_value=completed) as run,
    ):
        CodexService().run("do it")

    command = run.call_args.args[0]
    assert "--skip-git-repo-check" in command
    assert run.call_args.kwargs["cwd"] is None


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
