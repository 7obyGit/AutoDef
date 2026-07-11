from typing import Callable, Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def auto(f: F) -> F:
    """
    Placeholder for @auto decorator.
    Will generate function body at runtime based on description using LLM.
    """
    return f


def func(f: F) -> F:
    """
    Placeholder for @func decorator.
    All queries are passed directly to LLMs and the result is returned from an LLM.
    """
    return f

