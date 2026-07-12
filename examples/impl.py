from pydantic import BaseModel

from autodef import impl


class Person(BaseModel):
    name: str
    age: int
    occupation: str


@impl(debug=True)  # type: ignore[untyped-decorator]
def generate_person(description: str, age: int) -> Person:
    """
    Generate a person profile based on the given description.
    """
    return Person(name="", age=0, occupation="")


def main() -> None:
    print("Running @impl example...")
    try:
        person = generate_person("A 30-year-old software engineer named Alice.", 23)
        print(f"Generated Person: {person}")
    except Exception as e:
        print(f"Error: {e}")
        print(
            "Note: This example requires an LLM server (like LM Studio) running at http://localhost:1234/v1"
        )


if __name__ == "__main__":
    main()
