import logging

from autodef import shim

# Configure logging to see the shim process
logging.basicConfig(level=logging.DEBUG)


@shim(debug=True)  # type: ignore[untyped-decorator]
def parse_date_flexible(date_str: str) -> str:
    """
    Parse a date string and return it in YYYY-MM-DD format.
    The original implementation only handles YYYY/MM/DD.
    The @shim decorator should help it handle other formats (like DD-MM-YYYY) when it fails.
    """
    import datetime

    return datetime.datetime.strptime(date_str, "%Y/%m/%d").strftime("%Y-%m-%d")


if __name__ == "__main__":
    print("--- Test 1: Supported format ---")
    print(f"'2023/10/27' -> {parse_date_flexible('2023/10/27')}")

    print("\n--- Test 2: Unsupported format (triggers recovery) ---")
    # This will fail (ValueError), then @shim will
    # automatically prompt the LLM to fix it.
    # The LLM might provide a 'before' shim to normalize the input,
    # or a 'rewrite' to use a more flexible parsing logic.
    result = parse_date_flexible("27-10-2023")
    print(f"'27-10-2023' (recovered) -> {result}")
