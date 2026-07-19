import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from autodef.services.provider import ProviderService

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Default service instance for decorators
_default_service = ProviderService()

CACHE_DIR = Path(os.environ.get("AUTODEF_CACHE_DIR", ".autodef_cache"))
