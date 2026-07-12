import json
from typing import Any
from unittest.mock import MagicMock

from pydantic import BaseModel

from autodef.model.prompt import Prompt
from autodef.services.text_generator import TextGeneratorService


def test_text_generator_service_generate_text() -> None:
    # Setup mock
    service = TextGeneratorService(api_key="test", base_url="http://test", model="test-model")
    mock_client = MagicMock()
    service.client = mock_client

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Generated text"))]
    mock_client.chat.completions.create.return_value = mock_response

    prompt: Prompt[Any] = Prompt(prompt="Hello")

    # Execute
    result = service.generate_text(prompt)

    # Assert
    assert result == "Generated text"
    mock_client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        ],
    )


class MockObject(BaseModel):
    name: str
    age: int


def test_text_generator_service_generate_object() -> None:
    # Setup mock
    service = TextGeneratorService(api_key="test", base_url="http://test", model="test-model")
    mock_client = MagicMock()
    service.client = mock_client

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"name": "John", "age": 30}'))]
    mock_client.chat.completions.create.return_value = mock_response

    prompt: Prompt[Any] = Prompt(prompt="Create a person")

    # Execute
    result = service.generate_object(prompt, MockObject)

    # Assert
    assert isinstance(result, MockObject)
    assert result.name == "John"
    assert result.age == 30

    schema = json.dumps(MockObject.model_json_schema(), indent=2)
    expected_system_prompt = f"You are a helpful assistant.\n\nYou must return only valid JSON that matches this schema:\n{schema}"

    mock_client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[
            {"role": "system", "content": expected_system_prompt},
            {"role": "user", "content": [{"type": "text", "text": "Create a person"}]},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "MockObject",
                "strict": True,
                "schema": MockObject.model_json_schema(),
            },
        },
    )
