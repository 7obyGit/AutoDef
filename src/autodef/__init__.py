try:
    from importlib.metadata import version
except ImportError:
    from importlib_metadata import version  # type: ignore

from autodef.config import _default_service
from autodef.decorators import impl, llm, shim

try:
    __version__ = version("autodef")
except Exception:
    __version__ = "0.0.0-development"

__all__ = ["impl", "llm", "shim", "_default_service"]
