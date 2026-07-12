from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Prompt[T: BaseModel](BaseModel):
    prompt: str
    system_prompt: str = "You are a helpful assistant."
    payload: T | None = None
    images: list[str] = []  # List of base64 encoded images

    def generate_prompt(self) -> str:
        if self.payload:
            payload_json = self.payload.model_dump_json(indent=2)
            return f"{self.prompt}\n\nPayload:\n{payload_json}"
        return self.prompt
