from pathlib import Path
from unittest.mock import patch

from autodef import llm


def test_llm_path_argument(tmp_path: Path) -> None:
    # Create a dummy file
    test_file = tmp_path / "test.txt"
    content = "Hello, world!" * 10
    test_file.write_text(content)

    @llm
    def process_file(file_path: Path) -> str:
        """Process this file."""
        return ""

    with patch("autodef.decorators.llm._default_service.generate_text") as mock_gen:
        mock_gen.return_value = "Processed"

        result = process_file(test_file)

        assert result == "Processed"
        mock_gen.assert_called_once()

        prompt = mock_gen.call_args[0][0].prompt
        assert "test.txt" in prompt
        assert str(len(content)) in prompt
        assert content in prompt


def test_llm_large_path_argument(tmp_path: Path) -> None:
    # Create a large file
    test_file = tmp_path / "large.txt"
    content = "A" * 30000
    test_file.write_text(content)

    @llm
    def process_large_file(file_path: Path) -> str:
        """Process this large file."""
        return ""

    with patch("autodef.decorators.llm._default_service.generate_text") as mock_gen:
        mock_gen.return_value = "Processed"
        process_large_file(test_file)
        prompt = mock_gen.call_args[0][0].prompt

        assert "large.txt" in prompt
        assert "30000 bytes" in prompt
        # Should only contain first 25000 chars
        assert "A" * 25000 in prompt
        assert "A" * 25001 not in prompt
