import base64
import inspect
import io
from pathlib import Path
from typing import Any


def get_arg_display_value(arg_name: str, value: Any) -> str:
    """Get a string representation of an argument value, with special handling for self/cls."""
    if arg_name in ["self", "cls"]:
        try:
            if hasattr(value, "__dict__"):
                return f"<{value.__class__.__name__} object with state: {value.__dict__}>"
            return str(value)
        except Exception:
            return str(value)
    return str(value)


def get_file_context(func: Any) -> tuple[Path | None, str | None]:
    """Get the file path and content where a function is defined."""
    try:
        file_path = Path(inspect.getfile(func)).absolute()
        file_content = file_path.read_text(encoding="utf-8", errors="ignore")
        return file_path, file_content
    except Exception:
        return None, None


def get_type_info(hints: dict[str, Any]) -> str:
    """Get information about Pydantic models and other custom classes in type hints."""
    type_info = []
    for _name, t in hints.items():
        if hasattr(t, "model_json_schema"):  # Pydantic model
            schema = t.model_json_schema()
            type_info.append(f"Type '{t.__name__}' is a Pydantic model with schema: {schema}")
        elif inspect.isclass(t) and t.__module__ != "builtins":
            type_info.append(f"Type '{t.__name__}' is an existing class.")

    if not type_info:
        return ""
    return "\nExisting types you MUST use (DO NOT redefine them):\n" + "\n".join(type_info)


def is_image(value: Any) -> bool:
    """Check if a value is likely a Pillow Image object without direct dependency."""
    return hasattr(value, "save") and hasattr(value, "format") and hasattr(value, "mode")


def process_image(value: Any) -> str | None:
    """Convert an image (Pillow or path) to a base64 string."""
    # Handle Path or string path
    if isinstance(value, (Path, str)):
        p = Path(value)
        if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            try:
                with open(p, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return None

    # Handle Pillow Image
    if is_image(value):
        try:
            buffered = io.BytesIO()
            # If it's a Pillow image, it should have a save method
            # We use PNG as default format if not specified
            fmt = getattr(value, "format", "PNG") or "PNG"
            value.save(buffered, format=fmt)
            return base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception:
            return None

    return None
