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
from autodef.services.context_builder import get_arg_display_value, get_file_context, get_type_info

logger = logging.getLogger(__name__)


def impl(f: F | None = None, *, debug: bool = False) -> Any:
    """
    Decorator that generates the function body at runtime based on its description and signature.

    Uses an LLM to generate the Python code for the function, then executes it.
    The generated function is cached and reused for subsequent calls.
    It also persists the generated code to a local cache directory.

    Args:
        f: The function to decorate.
        debug: If True, enables debug logging for the decorator's internal operations.

    Returns:
        A wrapped version of the function that executes the generated code.

    Raises:
        RuntimeError: If the LLM fails to generate a valid function.
    """

    def decorator(func: F) -> F:
        generated_func: Callable[..., Any] | None = None

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
        cache_subdir = CACHE_DIR / func.__name__
        cache_file = cache_subdir / f"{context_hash}.py"

        if debug:
            logger.debug(f"Initializing impl for {func.__name__}")
            logger.debug(f"Cache file: {cache_file}")

        # Get file context for the prompt
        file_path, file_content = get_file_context(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal generated_func

            def get_implementation(
                error_info: str | None = None, broken_code: str | None = None
            ) -> tuple[Callable[..., Any], str]:
                nonlocal generated_func
                code = None

                # Try to load from persistent cache if no error_info is provided
                if error_info is None and cache_file.exists():
                    if debug:
                        logger.debug(f"Loading cached code for {func.__name__} from {cache_file}")
                    code = cache_file.read_text()

                if code is None:
                    if debug:
                        logger.debug(f"Generating new code for {func.__name__}...")

                    types_str = get_type_info(hints)

                    # Special handling for self and cls to show their state if available
                    method_context = ""
                    sig_params = list(sig.parameters.keys())
                    if args and sig_params:
                        # Try to find self or cls
                        for i, param_name in enumerate(sig_params):
                            if i < len(args) and param_name in ["self", "cls"]:
                                val = get_arg_display_value(param_name, args[i])
                                method_context += f"\nCurrent state of '{param_name}': {val}"
                    elif "self" in kwargs or "cls" in kwargs:
                        for param_name in ["self", "cls"]:
                            if param_name in kwargs:
                                val = get_arg_display_value(param_name, kwargs[param_name])
                                method_context += f"\nCurrent state of '{param_name}': {val}"

                    file_context_str = ""
                    if file_path:
                        file_context_str = f"\nFile Context:\n- Path: {file_path}\n- Content:\n---\n{file_content}\n---\n"

                    llm_usage_example = (
                        "\nExample of using @llm for tasks requiring AI/reasoning:\n"
                        "```python\n"
                        "import os\n"
                        "from autodef import llm\n"
                        "from pydantic import BaseModel\n"
                        "\n"
                        "class AnalysisResult(BaseModel):\n"
                        "    summary: str\n"
                        "    score: float\n"
                        "\n"
                        "@llm\n"
                        "def _ai_analyze(data: str) -> AnalysisResult:\n"
                        '    """Perform complex AI-based analysis on the data and return structured result."""\n'
                        "    ...\n"
                        "\n"
                        "def my_function(data: str):\n"
                        "    # 1. Procedural logic: read file\n"
                        "    # 2. AI logic: call the @llm helper you defined above\n"
                        "    # IMPORTANT: The @llm helper MUST have an empty body (...), the @llm decorator will ensure that an llm is called to do the work of the function, just provide a detailed docstring explaining what is needed to transform the input to the output of the function (what the function behaviour should look like)\n"
                        "    result = _ai_analyze(data)\n"
                        '    return result.summary if result.score > 0.5 else "Insufficient quality"\n'
                        "```\n"
                    )

                    error_context = ""
                    if error_info:
                        error_context = (
                            f"\nATTENTION: The previous implementation failed with the following error:\n"
                            f"Error:\n{error_info}\n"
                            f"Broken Code:\n---\n{broken_code}\n---\n"
                            f"Please fix the implementation to resolve this error.\n"
                        )

                    prompt_text = (
                        f"Write a Python function named '{func.__name__}' that matches this signature: "
                        f"def {func.__name__}{sig}:\n"
                        f'    """{doc.strip()}"""\n'
                        f"{types_str}\n"
                        f"{method_context}\n"
                        f"{file_context_str}\n"
                        f"{error_context}\n"
                        "IMPORTANT: If the signature contains 'self' or 'cls', you MUST include them in your function definition. "
                        "The types listed above are already defined and available in the environment. "
                        "DO NOT redefine them in your response. "
                        "The code must use the existing definitions directly by their name. "
                        "Do not use module prefixes like '__main__.' or the module name where they were defined. "
                        "Redefining these types will cause the production system to crash. "
                        "\n"
                        "CRITICAL REQUIREMENT: If the docstring requires natural language understanding, reasoning, "
                        "summarization, or complex distillation (AI-like tasks), you MUST use the `@llm` decorator. "
                        "Do NOT attempt to simulate or hardcode AI behavior with string manipulation. "
                        "You MUST DEFINE a helper function with `@llm` and a clear docstring INSIDE your response, "
                        "then call it from your main function. Do not assume any helper functions exist unless you define them. "
                        "Functions decorated with `@llm` MUST have an empty body (only `...`). "
                        "The logic for these functions is automatically handled by the `@llm` decorator at runtime. "
                        "The `@llm` decorator is already available in your namespace. "
                        f"{llm_usage_example}\n"
                        "\n"
                        "This code is for a production environment. "
                        "You must fully implement the logic described in the docstring. "
                        "Include any necessary imports at the top of your response (but do not import or define the existing types listed above). "
                        "Ensure the implementation is robust and handles relevant edge cases. "
                        "Return ONLY the Python code, with no explanations, no markdown code blocks, "
                        "and no extra text."
                    )

                    prompt: Prompt[Any] = Prompt(prompt=prompt_text)
                    if debug:
                        logger.debug(f"Prompting LLM for {func.__name__} with:\n{prompt_text}")
                    code = _default_service.generate_text(prompt)
                    if debug:
                        logger.debug(f"LLM returned code for {func.__name__}:\n{code}")

                    # Clean up the code
                    if "```python" in code:
                        code = code.split("```python")[1].split("```")[0]
                    elif "```" in code:
                        code = code.split("```")[1].split("```")[0]

                    # Ensure the code is not indented (sometimes LLMs return indented code)
                    lines = code.splitlines()
                    if lines:
                        # Find the first non-empty line
                        first_line = next((line for line in lines if line.strip()), None)
                        if first_line and first_line.startswith((" ", "\t")):
                            # Determine indentation level
                            indent = len(first_line) - len(first_line.lstrip())
                            code = "\n".join(
                                line[indent:] if len(line) >= indent else line.lstrip()
                                for line in lines
                            )

                exec_namespace = func.__globals__.copy()
                if "__main__" not in exec_namespace and "__main__" in sys.modules:
                    exec_namespace["__main__"] = sys.modules["__main__"]

                if "llm" not in exec_namespace:
                    from autodef import llm as _llm

                    exec_namespace["llm"] = _llm

                try:
                    # Capture the namespace before exec to detect syntax errors
                    exec(code, exec_namespace)
                    new_func = exec_namespace.get(func.__name__)
                    if not new_func:
                        raise RuntimeError(
                            f"Failed to generate function '{func.__name__}' from LLM response."
                        )

                    # Save successful code to cache (including successful retries during generation)
                    try:
                        cache_subdir.mkdir(parents=True, exist_ok=True)
                        cache_file.write_text(code)
                        if debug:
                            logger.debug(
                                f"Saved implementation code for {func.__name__} to {cache_file}"
                            )
                    except Exception as e_save:
                        logger.warning(f"Failed to save implementation code to cache: {e_save}")

                    return new_func, code
                except (SyntaxError, NameError, TypeError):
                    if error_info is None:  # Only retry once
                        logger.warning(
                            f"Failed to compile/parse generated code for {func.__name__}. Retrying..."
                        )
                        return get_implementation(
                            error_info=traceback.format_exc(), broken_code=code
                        )
                    raise
                except Exception:
                    if error_info is None:  # Only retry once
                        logger.warning(
                            f"Failed to execute generated code for {func.__name__}. Retrying..."
                        )
                        return get_implementation(
                            error_info=traceback.format_exc(), broken_code=code
                        )
                    raise

            if generated_func is None:
                generated_func, _ = get_implementation()

            try:
                return generated_func(*args, **kwargs)
            except Exception as e:
                if debug:
                    logger.debug(f"Error during execution of {func.__name__}: {e}")

                # Attempt to re-implement once
                error_info = traceback.format_exc()
                # We need the code that failed. Since we don't have it easily here if it was cached,
                # we might need to read it from cache or keep track of it.
                failed_code = (
                    cache_file.read_text() if cache_file.exists() else "Unknown (likely not cached)"
                )

                logger.warning(
                    f"Function {func.__name__} failed during execution. Attempting re-implementation..."
                )
                try:
                    reimplemented_func, new_code = get_implementation(
                        error_info=error_info, broken_code=failed_code
                    )
                    # Update state with fixed function
                    generated_func = reimplemented_func
                    return generated_func(*args, **kwargs)
                except Exception as retry_err:
                    logger.error(f"Re-implementation failed for {func.__name__}: {retry_err}")
                    raise e from retry_err  # Raise original error

        return wrapper  # type: ignore[return-value]

    if f is None:
        return decorator
    return decorator(f)
