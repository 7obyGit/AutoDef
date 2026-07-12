import json
import logging
import os
from typing import Any, TypeVar

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionUserMessageParam
from pydantic import BaseModel

from autodef.model.prompt import Prompt

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class TextGeneratorService:
    """
    Service for generating text and structured objects using an LLM.
    """

    def __init__(
        self, api_key: str | None = None, base_url: str | None = None, model: str | None = None
    ):
        """
        Initialize the service.

        Args:
            api_key: The API key for the LLM service. If not provided,
                     defaults to the AUTODEF_API_KEY environment variable.
            base_url: The base URL for the LLM service. If not provided,
                      defaults to the AUTODEF_BASE_URL environment variable.
            model: The name of the model to use. If not provided,
                   defaults to the AUTODEF_MODEL environment variable.
        """
        self.api_key = api_key or os.environ.get("AUTODEF_API_KEY", "N/a")
        self.base_url = base_url or os.environ.get("AUTODEF_BASE_URL", "http://localhost:1234/v1")
        self.model = model or os.environ.get("AUTODEF_MODEL", "Any")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_text(self, prompt: Prompt[Any]) -> str:
        """
        Generate a raw text response from the LLM.

        Args:
            prompt: The prompt object containing the instruction and optional payload.

        Returns:
            The raw text response from the LLM.
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": prompt.system_prompt},
        ]

        user_content: list[Any] = [{"type": "text", "text": prompt.generate_prompt()}]

        for image_base64 in prompt.images:
            user_content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            )

        user_message: ChatCompletionUserMessageParam = {"role": "user", "content": user_content}
        messages.append(user_message)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    def generate_object(self, prompt: Prompt[Any], object_type: type[T]) -> T:
        """
        Generate a structured object (Pydantic model) from the LLM.

        Args:
            prompt: The prompt object.
            object_type: The Pydantic model class to instantiate.

        Returns:
            An instance of object_type.
        """
        schema = json.dumps(object_type.model_json_schema(), indent=2)
        system_prompt = f"{prompt.system_prompt}\n\nYou must return only valid JSON that matches this schema:\n{schema}"

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system_prompt},
        ]

        user_content: list[Any] = [{"type": "text", "text": prompt.generate_prompt()}]

        for image_base64 in prompt.images:
            user_content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}}
            )

        user_message: ChatCompletionUserMessageParam = {"role": "user", "content": user_content}
        messages.append(user_message)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": object_type.__name__,
                    "strict": True,
                    "schema": object_type.model_json_schema(),
                },
            },
        )

        content = response.choices[0].message.content or "{}"
        return object_type.model_validate_json(content)
