import functools
import inspect
import logging
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel

from autodef.config import F, _default_service
from autodef.model.prompt import Prompt
from autodef.services.context_builder import get_arg_display_value, process_image

logger = logging.getLogger(__name__)


def llm(f: F | None = None, *, debug: bool = False) -> Any:
    """
    Decorator that passes all queries directly to an LLM and returns the result.

    If the return type is a Pydantic model, it returns a structured object by using
    structured output (JSON schema) from the LLM.
    Otherwise, it returns the raw text response.

    Args:
        f: The function to decorate.
        debug: If True, enables debug logging.

    Returns:
        The result from the LLM, either as a raw string or a Pydantic model.
    """

    def decorator(func: F) -> F:
        return_type = get_type_hints(func).get("return")

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Construct payload from arguments
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            doc = func.__doc__ or "Process the request."
            prompt_text = f"Task: {doc.strip()}"
            images = []

            if bound_args.arguments:
                display_args = {}
                for name, value in bound_args.arguments.items():
                    # Check for images
                    img_base64 = process_image(value)
                    if img_base64:
                        images.append(img_base64)
                        display_args[name] = f"<Image data for {name}>"
                        continue

                    display_args[name] = get_arg_display_value(name, value)

                    # Automatically read Path contents and metadata if it's not an image
                    if isinstance(value, Path):
                        try:
                            file_name = value.name
                            file_size = value.stat().st_size
                            content = ""
                            if value.is_file():
                                try:
                                    with open(value, encoding="utf-8", errors="ignore") as f:
                                        content = f.read(25000)
                                except Exception:
                                    pass

                            path_info = f"\n\nFile Argument '{name}':\n- Name: {file_name}\n- Size: {file_size} bytes"
                            if content:
                                path_info += (
                                    f"\n- Content (first 25000 chars):\n---\n{content}\n---"
                                )
                            else:
                                path_info += "\n- Content: [Empty or could not be read as text]"

                            prompt_text += path_info
                        except Exception as e:
                            if debug:
                                logger.debug(f"Error reading path argument {name} ({value}): {e}")

                prompt_text += f"\nInput: {display_args}"

            prompt: Prompt[Any] = Prompt(prompt=prompt_text, images=images)

            if debug:
                logger.debug(f"llm decorator: Processing {func.__name__}")
                logger.debug(f"Prompt:\n{prompt_text}")
                if images:
                    logger.debug(f"Included {len(images)} images in prompt.")

            result: Any
            if return_type and inspect.isclass(return_type) and issubclass(return_type, BaseModel):
                if debug:
                    logger.debug(f"Expecting Pydantic model: {return_type.__name__}")
                result = _default_service.generate_object(prompt, return_type)
            else:
                if debug:
                    logger.debug("Expecting raw text response")
                result = _default_service.generate_text(prompt)

            if debug:
                logger.debug(f"Result:\n{result}")

            return result

        return wrapper  # type: ignore[return-value]

    if f is None:
        return decorator
    return decorator(f)
