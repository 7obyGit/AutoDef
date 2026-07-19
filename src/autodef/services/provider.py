from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from autodef.model.prompt import Prompt
from autodef.services.codex import CodexService, TaskResult
from autodef.services.text_generator import TextGeneratorService


class ProviderService:
    """Route decorator requests to Codex or the existing OpenAI-compatible service."""

    def __init__(self) -> None:
        self.provider = os.environ.get("AUTODEF_PROVIDER", "auto").lower()
        self.lmstudio = TextGeneratorService()
        self.codex = CodexService()

    def _text_service(self, prompt: Prompt[Any]) -> TextGeneratorService | CodexService:
        if self.provider == "lmstudio":
            return self.lmstudio
        if self.provider == "codex":
            return self.codex
        return self.codex if shutil.which(self.codex.command) else self.lmstudio

    def generate_text(self, prompt: Prompt[Any]) -> str:
        return self._text_service(prompt).generate_text(prompt)

    def generate_object(self, prompt: Prompt[Any], object_type: type[BaseModel]) -> Any:
        return self._text_service(prompt).generate_object(prompt, object_type)

    def run_task(
        self,
        instruction: str,
        *,
        cwd: Path | None = None,
        sandbox: str = "read-only",
        model: str | None = None,
        image_values: Sequence[Any] = (),
    ) -> TaskResult:
        return self.codex.run_task(
            instruction,
            cwd=cwd,
            sandbox=sandbox,
            model=model,
            image_values=image_values,
        )
