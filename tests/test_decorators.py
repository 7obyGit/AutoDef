import shutil
from unittest.mock import patch

from pydantic import BaseModel

from autodef import impl, llm
from autodef.config import CACHE_DIR


class Person(BaseModel):
    name: str
    age: int


def test_impl_decorator() -> None:
    # Clear cache for this function to ensure LLM is called
    cache_subdir = CACHE_DIR / "get_person"
    if cache_subdir.exists():
        shutil.rmtree(cache_subdir)

    @impl
    def get_person(name: str) -> Person:
        """Create a person."""
        return Person(name="", age=0)

    # Mock response from LLM providing the function body
    mock_code = """
from pydantic import BaseModel
class Person(BaseModel):
    name: str
    age: int

def get_person(name: str) -> Person:
    return Person(name=name, age=30)
"""

    with patch("autodef.decorators.impl._default_service.generate_text") as mock_gen:
        mock_gen.return_value = mock_code

        result = get_person("Alice")

        assert result.name == "Alice"
        assert result.age == 30
        mock_gen.assert_called_once()
        # Verify prompt contains name
        prompt = mock_gen.call_args[0][0]
        assert "get_person" in prompt.prompt


def test_llm_decorator_text() -> None:
    @llm
    def simple_task(query: str) -> str:
        """Do something."""
        return ""

    with patch("autodef.decorators.llm._default_service.generate_text") as mock_gen:
        mock_gen.return_value = "Result"

        result = simple_task("test query")

        assert result == "Result"
        mock_gen.assert_called_once()


def test_llm_decorator_structured() -> None:
    @llm
    def structured_task(query: str) -> Person:
        """Return a person."""
        return Person(name="", age=0)

    with patch("autodef.decorators.llm._default_service.generate_object") as mock_gen:
        mock_person = Person(name="Bob", age=25)
        mock_gen.return_value = mock_person

        result = structured_task("Bob")

        assert result == mock_person
        mock_gen.assert_called_once()
