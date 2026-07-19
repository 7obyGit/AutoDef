from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from autodef.model.prompt import Prompt


class CodexUnavailableError(RuntimeError):
    """Raised when the Codex CLI is not available."""


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

    def __init__(self, command: str | None = None, model: str | None = None):
        self.command = command or os.environ.get("AUTODEF_CODEX_COMMAND", "codex")
        self.model = model or os.environ.get("AUTODEF_CODEX_MODEL")

    @property
    def available(self) -> bool:
        return shutil.which(self.command) is not None

    def generate_text(self, prompt: Prompt[Any], *, cwd: Path | None = None) -> str:
        return self.run(self._prompt_text(prompt), cwd=cwd).output

    def generate_object(
        self, prompt: Prompt[Any], object_type: type[BaseModel], *, cwd: Path | None = None
    ) -> BaseModel:
        with tempfile.TemporaryDirectory(prefix="autodef-codex-") as temp_dir:
            schema_path = Path(temp_dir) / "schema.json"
            output_path = Path(temp_dir) / "output.json"
            schema_path.write_text(json.dumps(object_type.model_json_schema()))
            result = self.run(
                self._prompt_text(prompt),
                cwd=cwd,
                output_schema=schema_path,
                output_path=output_path,
            )
            content = output_path.read_text() if output_path.exists() else result.output
            return object_type.model_validate_json(content)

    @staticmethod
    def _prompt_text(prompt: Prompt[Any]) -> str:
        return f"System instructions:\n{prompt.system_prompt}\n\n{prompt.generate_prompt()}"

    def run(
        self,
        instruction: str,
        *,
        cwd: Path | None = None,
        sandbox: str = "read-only",
        output_schema: Path | None = None,
        output_path: Path | None = None,
        model: str | None = None,
    ) -> TaskResult:
        if not self.available:
            raise CodexUnavailableError(
                f"Codex CLI '{self.command}' was not found. Install Codex or select the LM Studio provider."
            )

        command = [self.command, "exec", "--json", "--ephemeral", "--sandbox", sandbox]
        if cwd is not None:
            command.extend(["-C", str(cwd)])
        if model or self.model:
            command.extend(["--model", model or self.model or ""])
        if output_schema is not None:
            command.extend(["--output-schema", str(output_schema)])
        if output_path is not None:
            command.extend(["--output-last-message", str(output_path)])
        command.append(instruction)

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
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
            if (
                event_type == "item.completed"
                and isinstance(item, dict)
                and item.get("type") == "agent_message"
            ):
                final_output = str(item.get("text", ""))

        if output_path and output_path.exists():
            final_output = output_path.read_text()
        if completed.returncode != 0:
            detail = completed.stderr.strip() or final_output or "Codex task failed."
            raise RuntimeError(f"Codex exited with status {completed.returncode}: {detail}")
        return TaskResult(final_output, tuple(events), completed.returncode, thread_id)
