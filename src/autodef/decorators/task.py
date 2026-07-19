from __future__ import annotations

import functools
import inspect
from pathlib import Path
from typing import Any

from autodef.config import F, _default_service
from autodef.services.codex import TaskResult
from autodef.services.context_builder import get_arg_display_value


def task(
    f: F | None = None,
    *,
    sandbox: str = "read-only",
    cwd: str | Path | None = None,
    model: str | None = None,
    debug: bool = False,
) -> Any:
    """Run a function's documented task through Codex without interactive input."""

    def decorator(func: F) -> F:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> TaskResult:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            arguments = {
                name: get_arg_display_value(name, value)
                for name, value in bound.arguments.items()
            }
            instruction = (
                "Complete the following task autonomously. Do not ask the user for input.\n\n"
                f"Task: {(func.__doc__ or 'Complete the requested task.').strip()}\n"
                f"Arguments: {arguments}\n\n"
                "Use the repository's existing conventions and AGENTS.md instructions. "
                "Return a concise final report describing the work completed, files changed, "
                "tests run, and any remaining issues."
            )
            if debug:
                import logging

                logging.getLogger(__name__).debug("Running task %s:\n%s", func.__name__, instruction)
            return _default_service.run_task(
                instruction,
                cwd=Path(cwd) if cwd else None,
                sandbox=sandbox,
                model=model,
            )

        return wrapper  # type: ignore[return-value]

    if f is None:
        return decorator
    return decorator(f)
