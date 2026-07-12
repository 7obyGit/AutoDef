import base64
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from autodef.decorators.llm import llm
from autodef.model.prompt import Prompt


# Mock Pillow Image
class MockImage:
    def __init__(self) -> None:
        self.format = "PNG"
        self.mode = "RGB"

    def save(self, buffered: Any, format: str | None = None) -> None:  # noqa: A002
        buffered.write(b"fake_image_data")


def test_image_support() -> None:
    # Mock the service to capture the prompt
    mock_service = MagicMock()
    mock_service.generate_text.return_value = "Result with image"

    with patch("autodef.decorators.llm._default_service", mock_service):

        @llm
        def process_image_func(img: Any) -> str:
            """Tell me what is in this image."""
            return ""

        # Test with MockImage
        image = MockImage()
        process_image_func(image)

        # Verify prompt contained image data
        assert mock_service.generate_text.called
        prompt = mock_service.generate_text.call_args[0][0]
        assert isinstance(prompt, Prompt)
        assert len(prompt.images) == 1
        assert prompt.images[0] == base64.b64encode(b"fake_image_data").decode("utf-8")
        assert "Input: {'img': '<Image data for img>'}" in prompt.prompt


def test_image_path_support(tmp_path: Path) -> None:
    # Create a dummy image file
    img_path = tmp_path / "test.png"
    img_path.write_bytes(b"dummy_png_data")

    mock_service = MagicMock()
    mock_service.generate_text.return_value = "Result with image path"

    with patch("autodef.decorators.llm._default_service", mock_service):

        @llm
        def process_image_path(img_path: Path) -> str:
            """Tell me what is in this image file."""
            return ""

        process_image_path(img_path)

        assert mock_service.generate_text.called
        prompt = mock_service.generate_text.call_args[0][0]
        assert len(prompt.images) == 1
        assert prompt.images[0] == base64.b64encode(b"dummy_png_data").decode("utf-8")


if __name__ == "__main__":
    from typing import Any

    pytest.main([__file__])
