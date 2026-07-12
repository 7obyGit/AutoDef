import functools
import hashlib
import inspect
import json
import logging
import sys
import traceback
from collections.abc import Callable
from typing import Any, get_type_hints

from autodef.config import CACHE_DIR, F, _default_service
from autodef.model.prompt import Prompt
from autodef.services.context_builder import get_arg_display_value

logger = logging.getLogger(__name__)


def shim(f: F | None = None, *, debug: bool = False) -> Any:
    """
    Decorator that catches errors in the decorated function and attempts to fix them
    by generating 'before', 'after', or 'rewrite' code using an LLM.

    Args:
        f: The function to decorate.
        debug: If True, enables debug logging.

    Returns:
        A wrapped version of the function with error recovery capabilities.
    """

    def decorator(func: F) -> F:
        # State for shims and rewrites
        shim_before: Callable[..., Any] | None = None
        shim_after: Callable[..., Any] | None = None
        rewritten_func: Callable[..., Any] | None = None

        # Compute a hash for the function context to use as a cache key
        sig = inspect.signature(func)
        hints = get_type_hints(func)
        doc = func.__doc__ or ""

        # We serialize the parts of the function that define its behavior
        # to ensure the cache is invalidated if they change.
        context = {
            "name": func.__name__,
            "signature": str(sig),
            "docstring": doc.strip(),
            "hints": {k: str(v) for k, v in hints.items()},
        }
        context_json = json.dumps(context, sort_keys=True)
        context_hash = hashlib.sha256(context_json.encode()).hexdigest()
        cache_subdir = CACHE_DIR / f"{func.__name__}_shim"
        cache_file = cache_subdir / f"{context_hash}.py"

        if debug:
            logger.debug(f"Initializing shim for {func.__name__}")
            logger.debug(f"Cache file: {cache_file}")

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal shim_before, shim_after, rewritten_func

            # Try to load from persistent cache if available and not already loaded
            if not (shim_before or shim_after or rewritten_func) and cache_file.exists():
                if debug:
                    logger.debug(f"Loading cached shims for {func.__name__} from {cache_file}")
                try:
                    cached_code = cache_file.read_text()
                    exec_namespace = func.__globals__.copy()
                    if "__main__" not in exec_namespace and "__main__" in sys.modules:
                        exec_namespace["__main__"] = sys.modules["__main__"]

                    exec(cached_code, exec_namespace)
                    shim_before = exec_namespace.get("shim_before")
                    shim_after = exec_namespace.get("shim_after")
                    rewritten_func = exec_namespace.get(func.__name__)
                except Exception as e_cache:
                    logger.warning(f"Failed to load cached shim for {func.__name__}: {e_cache}")

            current_args = args
            current_kwargs = kwargs

            # 1. Apply 'before' shim if it exists
            if shim_before:
                try:
                    current_args, current_kwargs = shim_before(*current_args, **current_kwargs)
                except Exception as e_before:
                    if debug:
                        logger.debug(f"Shim 'before' failed for {func.__name__}: {e_before}")

            try:
                # 2. Execute main body (either original or rewritten)
                if rewritten_func:
                    result = rewritten_func(*current_args, **current_kwargs)
                else:
                    result = func(*current_args, **current_kwargs)

                # 3. Apply 'after' shim if it exists
                if shim_after:
                    try:
                        result = shim_after(result, *current_args, **current_kwargs)
                    except Exception as e_after:
                        if debug:
                            logger.debug(f"Shim 'after' failed for {func.__name__}: {e_after}")

                return result

            except Exception as e:
                # 4. Main body failed. Attempt recovery.
                error_info = traceback.format_exc()
                if debug:
                    logger.debug(
                        f"Function {func.__name__} failed: {e}. Attempting shim recovery..."
                    )

                # Special handling for self and cls to show their state in input arguments
                display_args = list(current_args)
                display_kwargs = current_kwargs.copy()
                sig_params = list(sig.parameters.keys())

                # Try to identify self or cls in args
                for i, param_name in enumerate(sig_params):
                    if i < len(display_args) and param_name in ["self", "cls"]:
                        display_args[i] = get_arg_display_value(param_name, display_args[i])

                # Also check in kwargs just in case
                for param_name in ["self", "cls"]:
                    if param_name in display_kwargs:
                        display_kwargs[param_name] = get_arg_display_value(
                            param_name, display_kwargs[param_name]
                        )

                # Construct prompt for recovery
                prompt_text = (
                    f"The following Python function failed during execution:\n"
                    f"Function: {func.__name__}{sig}\n"
                    f"Docstring: {doc.strip()}\n"
                    f"Error:\n{error_info}\n"
                    f"Input Arguments: args={display_args}, kwargs={display_kwargs}\n"
                    "\n"
                    "You have three options to fix this issue:\n"
                    "1. 'before': Provide a function that pre-processes the inputs to avoid the error.\n"
                    "   Signature: `def shim_before(*args, **kwargs) -> tuple[tuple, dict]:` (returns updated args and kwargs)\n"
                    "2. 'after': Provide a function that post-processes the result or handles the error if possible.\n"
                    "   Signature: `def shim_after(result, *args, **kwargs) -> Any:` (returns the final result)\n"
                    "3. 'rewrite': Rewrite the entire function body to be more robust.\n"
                    "   Signature: `def {func.__name__}{sig}:` (same as original)\n"
                    "\n"
                    "IMPORTANT: If you choose 'rewrite', and the original signature contains 'self' or 'cls', you MUST include them in your function definition.\n"
                    "\n"
                    f"Choose the most appropriate strategy (you can provide one or more). "
                    "Your goal is to RECOVER from the error and ensure the function returns a valid result that satisfies its purpose/docstring. "
                    "Return ONLY the Python code for the chosen shims or rewrite. "
                    "Use the names `shim_before`, `shim_after`, and `{func.__name__}` for the rewrite. "
                    "Ensure all necessary imports are included. "
                    "Return ONLY the code, no explanations, no markdown blocks."
                )

                prompt: Prompt[Any] = Prompt(prompt=prompt_text)
                code = _default_service.generate_text(prompt)

                # Clean up the code
                if "```python" in code:
                    code = code.split("```python")[1].split("```")[0]
                elif "```" in code:
                    code = code.split("```")[1].split("```")[0]

                # Execute generated code to capture shims/rewrite
                exec_namespace = func.__globals__.copy()
                if "__main__" not in exec_namespace and "__main__" in sys.modules:
                    exec_namespace["__main__"] = sys.modules["__main__"]

                try:
                    if debug:
                        logger.debug(f"Executing recovery code:\n{code}")
                    exec(code, exec_namespace)
                    shim_before = exec_namespace.get("shim_before", shim_before)
                    shim_after = exec_namespace.get("shim_after", shim_after)
                    rewritten_func = exec_namespace.get(func.__name__, rewritten_func)

                    if debug:
                        logger.debug(
                            f"Captured: shim_before={shim_before}, shim_after={shim_after}, rewritten_func={rewritten_func}"
                        )

                    if not (shim_before or shim_after or rewritten_func):
                        raise RuntimeError("LLM failed to provide any recovery code.")

                    # Save successful recovery code to cache
                    try:
                        cache_subdir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(code)
                        if debug:
                            logger.debug(f"Saved recovery code for {func.__name__} to {cache_file}")
                    except Exception as e_save:
                        logger.warning(f"Failed to save recovery code to cache: {e_save}")

                    # Use the original arguments as the starting point for retry

                    # Retry once with the new shims/rewrite
                    def run_retry(
                        r_args: tuple[Any, ...],
                        r_kwargs: dict[str, Any],
                        r_before: Callable[..., Any] | None,
                        r_after: Callable[..., Any] | None,
                        r_rewrite: Callable[..., Any] | None,
                        error_info_retry: str | None = None,
                        broken_code: str | None = None,
                    ) -> Any:
                        try:
                            if r_before:
                                try:
                                    r_args, r_kwargs = r_before(*r_args, **r_kwargs)
                                except Exception as e_before:
                                    if debug:
                                        logger.debug(
                                            f"Shim 'before' failed during retry for {func.__name__}: {e_before}"
                                        )

                            res = r_rewrite(*r_args, **r_kwargs) if r_rewrite else func(*r_args, **r_kwargs)

                            if r_after:
                                try:
                                    res = r_after(res, *args, **kwargs)
                                except Exception as e_after:
                                    if debug:
                                        logger.debug(
                                            f"Shim 'after' failed during retry for {func.__name__}: {e_after}"
                                        )
                            return res
                        except Exception as e_retry:
                            if error_info_retry is None:
                                if debug:
                                    logger.debug(
                                        f"Retry failed for {func.__name__}: {e_retry}. Attempting one fix..."
                                    )

                                retry_prompt_text = (
                                    f"The recovery code you provided failed with the following error:\n"
                                    f"Error: {traceback.format_exc()}\n"
                                    f"Code provided:\n---\n{broken_code}\n---\n"
                                    "Please fix the code and return the FULL updated Python code for the shims/rewrite. "
                                    "Return ONLY the code, no explanations."
                                )
                                retry_prompt: Prompt[Any] = Prompt(prompt=retry_prompt_text)
                                new_code = _default_service.generate_text(retry_prompt)

                                if "```python" in new_code:
                                    new_code = new_code.split("```python")[1].split("```")[0]
                                elif "```" in new_code:
                                    new_code = new_code.split("```")[1].split("```")[0]

                                new_exec_ns = func.__globals__.copy()
                                if "__main__" not in new_exec_ns and "__main__" in sys.modules:
                                    new_exec_ns["__main__"] = sys.modules["__main__"]

                                exec(new_code, new_exec_ns)
                                nb = new_exec_ns.get("shim_before", r_before)
                                na = new_exec_ns.get("shim_after", r_after)
                                nr = new_exec_ns.get(func.__name__, r_rewrite)

                                # Save fixed recovery code to cache
                                try:
                                    cache_subdir.mkdir(parents=True, exist_ok=True)
                                    cache_file.write_text(new_code)
                                    if debug:
                                        logger.debug(
                                            f"Saved fixed recovery code for {func.__name__} to {cache_file}"
                                        )
                                except Exception as e_save:
                                    logger.warning(
                                        f"Failed to save fixed recovery code to cache: {e_save}"
                                    )

                                return run_retry(
                                    args,
                                    kwargs,
                                    nb,
                                    na,
                                    nr,
                                    error_info_retry=traceback.format_exc(),
                                    broken_code=new_code,
                                )
                            raise

                    return run_retry(
                        args, kwargs, shim_before, shim_after, rewritten_func, broken_code=code
                    )
                except Exception as retry_err:
                    logger.error(f"Recovery failed for {func.__name__}: {retry_err}")
                    raise e from retry_err

        return wrapper  # type: ignore[return-value]

    if f is None:
        return decorator
    return decorator(f)
