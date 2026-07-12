from pathlib import Path
from typing import Any

from autodef import llm


@llm
def describe_image(image: Any) -> str:
    """Describe the contents of the provided image in detail."""
    return ""


def main() -> None:
    # Path to the example image
    example_png = Path(__file__).parent / "example.png"

    if not example_png.exists():
        print(f"Error: {example_png} not found.")
        return

    print(f"--- Describing image: {example_png.name} ---")
    try:
        # Pass the Path object directly to the @llm function
        # AutoDef will detect it's an image, load it, and send it to the LLM
        description = describe_image(example_png)
        print(f"Description:\n{description}")
    except Exception as e:
        print(f"Error calling LLM: {e}")
        print("\nNote: Make sure your LLM provider supports vision and is correctly configured.")

    # Demonstration with Pillow (if installed)
    try:
        from PIL import Image

        print("\n--- Describing image using Pillow Image object ---")
        img_obj = Image.open(example_png)
        description = describe_image(img_obj)
        print(f"Description (from Pillow object):\n{description}")
    except ImportError:
        print("\nNote: Install 'pillow' to see demonstration with Image objects.")
    except Exception as e:
        print(f"Error with Pillow object: {e}")


if __name__ == "__main__":
    main()
