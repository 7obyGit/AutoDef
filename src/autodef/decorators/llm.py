import functools
import inspect
import logging
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, create_model

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
        if debug:
            logger.debug(
                f"llm decorator: Initialized for function '{func.__name__}' with return_type: {return_type}"
            )

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
                                path_info += f"\n- Content (first 25000 chars):\n---\n{content}\n---"
                            else:
                                path_info += (
                                    "\n- Content: [Empty or could not be read as text]"
                                )

                            prompt_text += path_info
                        except Exception as e:
                            if debug:
                                logger.debug(f"Error reading path argument {name} ({value}): {e}")

                prompt_text += f"\nInput: {display_args}"

            prompt: Prompt[Any] = Prompt(prompt=prompt_text, images=images)

            if debug:
                logger.debug(f"llm decorator: Processing {func.__name__}")
                logger.debug(f"Return type: {return_type}")
                logger.debug(f"Prompt:\n{prompt_text}")
                if images:
                    logger.debug(f"Included {len(images)} images in prompt.")

            result = _get_result(prompt, return_type, debug)

            if debug:
                logger.debug(f"Result:\n{result}")

            return result

        return wrapper  # type: ignore[return-value]

    if f is None:
        return decorator
    return decorator(f)


def _get_result(prompt: Prompt[Any], return_type: Any, debug: bool) -> Any:
    """Helper to determine the result based on return type."""
    # 1. No return type or explicit string
    if (
        not return_type
        or return_type is inspect.Signature.empty
        or return_type is str
    ):
        if debug:
            logger.debug("Branch: Raw text response (str or no return type)")
        return _default_service.generate_text(prompt)

    # 2. Pydantic model
    if inspect.isclass(return_type) and issubclass(return_type, BaseModel):
        if debug:
            logger.debug(f"Branch: Pydantic model detected ({return_type.__name__})")
        return _default_service.generate_object(prompt, return_type)

    # 3. Primitive types (int, float, bool)
    if return_type in (int, float, bool):
        if debug:
            logger.debug(
                f"Action: Wrapping primitive {return_type.__name__} in Pydantic model"
            )
        wrapper_model = create_model("Wrapper", value=(return_type, ...))
        wrapped_result = _default_service.generate_object(prompt, wrapper_model)
        return wrapped_result.value  # type: ignore[attr-defined]

    # 4. Regular classes
    if inspect.isclass(return_type):
        return _handle_regular_class(prompt, return_type, debug)

    # Fallback
    if debug:
        logger.debug(f"No specific handling for return type {return_type}, using raw text")
    return _default_service.generate_text(prompt)


def _handle_regular_class(prompt: Prompt[Any], return_type: type, debug: bool) -> Any:
    """Handle generation for a regular (non-Pydantic) class."""
    if debug:
        logger.debug(
            f"Action: Attempting to convert regular class {return_type.__name__} to Pydantic model"
        )

    try:
        hints = get_type_hints(return_type)
        if debug:
            logger.debug(f"Type hints for {return_type.__name__}: {hints}")

        if not hints:
            if debug:
                logger.debug(
                    f"Class {return_type.__name__} has no type hints, falling back to raw text"
                )
            return _default_service.generate_text(prompt)

        fields = {name: (typ, ...) for name, typ in hints.items()}
        dynamic_model = create_model(return_type.__name__, **fields)  # type: ignore

        if debug:
            logger.debug(
                f"Created dynamic Pydantic model: {dynamic_model.model_json_schema()}"
            )

        structured_data = _default_service.generate_object(prompt, dynamic_model)
        data_dict = structured_data.model_dump()

        # Instantiate the original class
        try:
            if debug:
                logger.debug(f"Instantiating {return_type.__name__} via constructor")
            return return_type(**data_dict)
        except TypeError:
            if debug:
                logger.debug(
                    f"Constructor failed for {return_type.__name__}, trying setattr"
                )
            instance = return_type()
            for name, value in data_dict.items():
                setattr(instance, name, value)
            return instance

    except Exception as e:
        if debug:
            logger.error(
                f"Could not use structured output for {return_type}: {e}", exc_info=True
            )
        return _default_service.generate_text(prompt)
