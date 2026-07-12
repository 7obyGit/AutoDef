from pathlib import Path

from autodef import llm


@llm(debug=True)  # type: ignore[untyped-decorator]
def summarize_file(file_path: Path) -> str:
    """
    Summarize the contents of the provided file.
    The LLM will automatically receive the file name, size, and the first 25,000 characters.
    """
    return ""


def main() -> None:
    # Use the project's README.md file as an example
    example_file = Path(__file__).parent.parent / "README.md"

    if not example_file.exists():
        print(f"Error: {example_file} not found.")
        return

    print(f"Summarizing file: {example_file.absolute()}")

    try:
        summary = summarize_file(example_file)
        print("\n--- Summary ---")
        print(summary)
        print("---------------")
    except Exception as e:
        print(f"\nError: {e}")
        print(
            "\nNote: This example requires an LLM server (like LM Studio) running at http://localhost:1234/v1"
        )
        print(
            "To run a local mock server for testing, you can use a tool like 'lms' or a simple Flask/FastAPI app."
        )

    # Cleanup (not needed since we are using README.md)


if __name__ == "__main__":
    main()
