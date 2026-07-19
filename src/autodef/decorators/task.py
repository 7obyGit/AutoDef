from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, overload

from autodef.config import _default_service
from autodef.services.codex import SandboxMode, TaskResult
from autodef.services.context_builder import get_arg_display_value


@overload
def task[**P](
    f: Callable[P, Any],
    *,
    sandbox: SandboxMode = "workspace-write",
    cwd: str | Path | None = None,
    model: str | None = None,
    debug: bool = False,
) -> Callable[P, TaskResult]: ...


@overload
def task[**P](
    f: None = None,
    *,
    sandbox: SandboxMode = "workspace-write",
    cwd: str | Path | None = None,
    model: str | None = None,
    debug: bool = False,
) -> Callable[[Callable[P, Any]], Callable[P, TaskResult]]: ...


def task[**P](
    f: Callable[P, Any] | None = None,
    *,
    sandbox: SandboxMode = "workspace-write",
    cwd: str | Path | None = None,
    model: str | None = None,
    debug: bool = False,
) -> Callable[P, TaskResult] | Callable[[Callable[P, Any]], Callable[P, TaskResult]]:
    """Run a function's documented task through Codex without interactive input."""

    def decorator(func: Callable[P, Any]) -> Callable[P, TaskResult]:
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> TaskResult:
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
                image_values=tuple(bound.arguments.values()),
            )

        return wrapper

    if f is None:
        return decorator
    return decorator(f) if f is not None else decorator
