from pydantic import BaseModel

from autodef import llm


class Translation(BaseModel):
    original: str
    translated: str
    language: str


@llm(debug=True)  # type: ignore[untyped-decorator]
def translate(text: str, target_language: str) -> str:
    """
    Translate the input text to the target language.
    """
    return ""


@llm(debug=True)  # type: ignore[untyped-decorator]
def translate_structured(text: str, target_language: str) -> Translation:
    """
    Translate the input text and return a structured response.
    """
    return Translation(original="", translated="", language="")


def main() -> None:
    print("Running @llm example...")
    try:
        # 1. Text response
        greeting = translate("Hello, how are you?", "French")
        print(f"Text Translation: {greeting}")

        # 2. Structured response
        translation_obj = translate_structured("Good morning", "Spanish")
        print(f"Structured Translation: {translation_obj}")
    except Exception as e:
        print(f"Error: {e}")
        print(
            "Note: This example requires an LLM server (like LM Studio) running at http://localhost:1234/v1"
        )


if __name__ == "__main__":
    main()
