from __future__ import annotations

import base64
import copy
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from autodef.model.prompt import Prompt

T = TypeVar("T", bound=BaseModel)
SandboxMode = Literal["read-only", "workspace-write", "danger-full-access"]
DEFAULT_CODEX_MODEL = "gpt-5.6-luna"
DEFAULT_CODEX_REASONING_EFFORT = "medium"


def _strict_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make object nodes compatible with Codex's strict structured-output schema."""
    strict_schema = copy.deepcopy(schema)

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            node["additionalProperties"] = False
            for property_schema in node.get("properties", {}).values():
                visit(property_schema)
        for key in ("$defs", "definitions"):
            for definition in node.get(key, {}).values():
                visit(definition)
        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            for option in node.get(key, []):
                visit(option)
        visit(node.get("items"))

    visit(strict_schema)
    return strict_schema


class CodexUnavailableError(RuntimeError):
    """Raised when the Codex CLI is not available."""


class CodexExecutionError(RuntimeError):
    """Raised when Codex cannot complete a task."""


@dataclass(frozen=True)
class CodexEvent:
    """One JSONL event emitted by a Codex run."""

    type: str
    data: dict[str, Any]


@dataclass(frozen=True)
class TaskResult:
    """The final output and metadata from a Codex task."""

    output: str
    events: tuple[CodexEvent, ...]
    returncode: int
    thread_id: str | None = None


class CodexService:
    """Invoke the installed Codex CLI in non-interactive mode."""

    def __init__(
        self,
        command: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
    ):
        self.command = command or os.environ.get("AUTODEF_CODEX_COMMAND", "codex")
        codex_config = self._load_config()
        self.model = (
            model
            or os.environ.get("AUTODEF_CODEX_MODEL")
            or self._config_string(codex_config, "model")
            or DEFAULT_CODEX_MODEL
        )
        self.reasoning_effort = (
            reasoning_effort
            or os.environ.get("AUTODEF_CODEX_REASONING_EFFORT")
            or self._config_string(codex_config, "model_reasoning_effort")
            or DEFAULT_CODEX_REASONING_EFFORT
        )

    @staticmethod
    def _load_config() -> dict[str, Any]:
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        config_path = codex_home / "config.toml"
        try:
            with config_path.open("rb") as config_file:
                config = tomllib.load(config_file)
        except (OSError, tomllib.TOMLDecodeError):
            return {}
        return config if isinstance(config, dict) else {}

    @staticmethod
    def _config_string(config: dict[str, Any], key: str) -> str | None:
        value = config.get(key)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _workspace_root(path: Path) -> Path | None:
        path = path.resolve()
        if path.is_file():
            path = path.parent
        for candidate in (path, *path.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    @classmethod
    def _execution_cwd(cls, cwd: Path | None) -> Path | None:
        if cwd is not None:
            return cwd
        return cls._workspace_root(Path.cwd())

    @property
    def available(self) -> bool:
        return shutil.which(self.command) is not None

    def generate_text(self, prompt: Prompt[Any], *, cwd: Path | None = None) -> str:
        with self._materialize_base64_images(prompt.images) as images:
            return self.run(self._prompt_text(prompt), cwd=cwd, images=images).output

    def generate_object(self, prompt: Prompt[Any], object_type: type[T], *, cwd: Path | None = None) -> T:
        with tempfile.TemporaryDirectory(prefix="autodef-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "output.json"
            schema_path.write_text(json.dumps(_strict_json_schema(object_type.model_json_schema())))
            with self._materialize_base64_images(prompt.images) as images:
                result = self.run(
                    self._prompt_text(prompt),
                    cwd=cwd,
                    output_schema=schema_path,
                    output_path=output_path,
                    images=images,
                )
            content = output_path.read_text() if output_path.exists() else result.output
            return object_type.model_validate_json(content)

    def run_task(
        self,
        instruction: str,
        *,
        cwd: Path | None = None,
        sandbox: SandboxMode = "workspace-write",
        model: str | None = None,
        image_values: Sequence[object] = (),
    ) -> TaskResult:
        with self._materialize_values_as_images(image_values) as images:
            return self.run(instruction, cwd=cwd, sandbox=sandbox, model=model, images=images)

    @staticmethod
    @contextmanager
    def _materialize_base64_images(images: Sequence[str]) -> Iterator[list[Path]]:
        with tempfile.TemporaryDirectory(prefix="autodef-codex-images-") as temp_dir:
            paths = []
            for index, image in enumerate(images):
                path = Path(temp_dir) / f"image-{index}.png"
                path.write_bytes(base64.b64decode(image))
                paths.append(path)
            yield paths

    @staticmethod
    @contextmanager
    def _materialize_values_as_images(values: Sequence[Any]) -> Iterator[list[Path]]:
        from autodef.services.context_builder import process_image

        with tempfile.TemporaryDirectory(prefix="autodef-codex-images-") as temp_dir:
            paths = []
            for index, value in enumerate(values):
                if isinstance(value, (str, Path)):
                    path = Path(value)
                    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                        continue
                    if path.is_file():
                        paths.append(path)
                        continue
                encoded = process_image(value)
                if encoded:
                    path = Path(temp_dir) / f"image-{index}.png"
                    path.write_bytes(base64.b64decode(encoded))
                    paths.append(path)
            yield paths

    @staticmethod
    def _prompt_text(prompt: Prompt[Any]) -> str:
        return f"System instructions:\n{prompt.system_prompt}\n\n{prompt.generate_prompt()}"

    def run(
        self,
        instruction: str,
        *,
        cwd: Path | None = None,
        sandbox: SandboxMode = "workspace-write",
        output_schema: Path | None = None,
        output_path: Path | None = None,
        model: str | None = None,
        images: Sequence[Path] = (),
    ) -> TaskResult:
        if not self.available:
            raise CodexUnavailableError(
                f"Codex CLI '{self.command}' was not found. Install Codex or select the LM Studio provider."
            )

        execution_cwd = self._execution_cwd(cwd)
        command = [self.command, "exec", "--json", "--ephemeral", "--sandbox", sandbox]
        if execution_cwd is not None:
            command.extend(["-C", str(execution_cwd)])
        else:
            command.append("--skip-git-repo-check")
        if model or self.model:
            command.extend(["--model", model or self.model or ""])
        if self.reasoning_effort:
            command.extend(["-c", f'model_reasoning_effort="{self.reasoning_effort}"'])
        if output_schema is not None:
            command.extend(["--output-schema", str(output_schema)])
        if output_path is not None:
            command.extend(["--output-last-message", str(output_path)])
        for image in images:
            command.extend(["--image", str(image)])
        command.append(instruction)

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                cwd=str(execution_cwd) if execution_cwd else None,
            )
        except OSError as error:
            raise CodexExecutionError(f"Unable to start Codex CLI '{self.command}': {error}") from error
        events: list[CodexEvent] = []
        final_output = ""
        thread_id: str | None = None
        for line in completed.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type", ""))
            events.append(CodexEvent(event_type, event))
            if event_type == "thread.started":
                thread_id = event.get("thread_id")
            item = event.get("item", {})
            if event_type == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
                final_output = str(item.get("text", ""))

        if output_path and output_path.exists():
            final_output = output_path.read_text()
        if completed.returncode != 0:
            details = [completed.stderr.strip()] if completed.stderr.strip() else []
            if final_output:
                details.append(f"last response: {final_output}")
            for event in events:
                if event.type == "error":
                    error_data = event.data.get("error") or event.data.get("message")
                    if error_data:
                        details.append(f"error event: {error_data}")
            detail = " | ".join(details) or "Codex task failed."
            raise CodexExecutionError(
                f"Codex exited with status {completed.returncode}. "
                "Check Codex authentication, repository location, and sandbox settings. "
                f"Details: {detail}"
            )
        return TaskResult(final_output, tuple(events), completed.returncode, thread_id)
