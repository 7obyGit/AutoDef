import logging
import os

from autodef import impl

# Configure logging to see the retry process
logging.basicConfig(level=logging.DEBUG)

# We'll use a specific cache directory for this example to demonstrate re-implementation
os.environ["AUTODEF_CACHE_DIR"] = ".example_cache"


@impl(debug=True)  # type: ignore[untyped-decorator]
def get_user_initials(full_name: str) -> str:
    """
    Extract the initials from a full name (e.g., 'John Doe' -> 'JD').
    Handles multiple names and mixed casing.

    IMPORTANT FOR LLM IMPLEMENTATION: In your first implementation, you MUST introduce
    a logical bug that throws an exception when the input is an empty string.
    Do NOT handle the empty string case properly in the first attempt.
    This is intentional to demonstrate the error correction mechanism.
    """
    return ""


if __name__ == "__main__":
    # The first call will trigger the LLM to implement the function.
    print(f"Initials for 'Alice Smith': {get_user_initials('Alice Smith')}")

    # This call with empty string will trigger error correction because the LLM
    # was instructed to intentionally fail on empty input in the first implementation.
    try:
        print(f"Initials for '': {get_user_initials('')}")
    except Exception as e:
        print(f"Failed even after retry: {e}")

    print("\nNote: To see error correction in action specifically, one would need a scenario ")
    print(
        "where the LLM's first attempt is syntactically correct but logically flawed for certain inputs, "
    )
    print("leading to a runtime error that triggers the retry mechanism.")
