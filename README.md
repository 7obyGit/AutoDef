# 🤖 AutoDef

AutoDef is a Python library that leverages Large Language Models (LLMs) to automatically implement, execute, and repair functions at runtime.
It transforms docstrings into executable code, providing a seamless bridge between declarative intent and imperative execution.

## ✨ Key Features

- **`@impl` Decorator**: Automatically generates function bodies from docstrings and type hints.
- **`@llm` Decorator**: Directly routes function calls to an LLM, supporting raw text and structured Pydantic responses.
- **`@shim` Decorator**: Intelligent error recovery that automatically repairs failing functions at runtime.
- **📦 Smart Caching**: Generated code is persisted locally, ensuring stability, predictability, and performance.
- **🔍 Context Awareness**: Automatically includes local file context and type definitions in prompts.
- **🖼️ Multimodal Support**: Seamlessly handle images and file paths as function arguments.

## 🚀 Quick Start

### Installation

```bash
pip install autodef
```

*Note: Requires Python 3.12 or higher.*

### Configuration

AutoDef works with any OpenAI-compatible API. Configure it via environment variables:

By default, local models will be used if available.

```bash
export AUTODEF_API_KEY="your-api-key"
export AUTODEF_BASE_URL="https://api.openai.com/v1"
export AUTODEF_MODEL="gpt-5"
export AUTODEF_CACHE_DIR=".autodef_cache"  # Optional, defaults to .autodef_cache

# Optional provider selection: auto, codex, or lmstudio
export AUTODEF_PROVIDER="auto"
```

## 🛠️ Usage Examples

### 1. Automatic Implementation (`@impl`)

Turn a description into code instantly. The implementation is generated once, cached, and reused.

```python
from autodef import impl

@impl
def get_weather_advice(celsius: float) -> str:
    """
    Returns a string advice based on the temperature.
    Use emoji and be friendly.
    """
    ...

print(get_weather_advice(25.5)) 
# Output: "It's a beautiful 25.5°C! Perfect for a walk. ☀️"
```

### 2. LLM-Backed Functions (`@llm`)

For tasks requiring natural language reasoning or multimodal input.

```python
from autodef import llm
from pydantic import BaseModel
from pathlib import Path

class Summary(BaseModel):
    title: str
    key_points: list[str]

@llm
def summarize_report(file_path: Path) -> Summary:
    """Summarize the provided report file."""
    ...

# AutoDef automatically reads the file content and sends it to the LLM
report_summary = summarize_report(Path("report.txt"))
```

### 3. Self-Healing Code (`@shim`)

Automatically recover from runtime errors using LLM-generated fixes.

```python
from autodef import shim

@shim
def parse_config(raw_data: str) -> dict:
    # This might fail if raw_data is malformed
    import json
    return json.loads(raw_data)

# If json.loads fails, @shim will ask the LLM to 
# provide a fix (before, after, or a full rewrite).
data = parse_config("{ invalid json }")
```

### 4. Autonomous Codex Tasks (`@task`)

When the Codex CLI is installed, `auto` selects it for the existing decorators and
`@task` can run a complete non-interactive coding-agent task. Tasks return the final
Codex report together with the emitted events and thread ID.

```python
from autodef import TaskResult, task

@task(sandbox="workspace-write")
def implement_change(request: str) -> TaskResult:
    """Implement the requested change, run the relevant tests, and report the result."""
    ...

result = implement_change("Add validation for duplicate usernames")
print(result.output)
```

Use `AUTODEF_PROVIDER=lmstudio` to force the existing LM Studio/OpenAI-compatible
integration, or `AUTODEF_PROVIDER=codex` to require Codex. Tasks default to Codex's
read-only sandbox; use `sandbox="workspace-write"` explicitly when edits are intended.

## 🧪 Development & Release

### Testing
This project uses `uv` for dependency management and `aw` for script execution, install using `npm install -g @7obygit/aw`.
You can run all standard checks (linting, type checking, and tests) using the provided helper script:

```bash
aw run check  # Runs ./.aw/check.sh
```

Alternatively, you can run them manually:

```bash
uv sync --dev
uv run ruff check .
uv run mypy .
uv run pytest
```

### Releasing to PyPI
Releases are automated via GitHub Actions using [Python Semantic Release](https://python-semantic-release.readthedocs.io/).

To trigger a new release:
1. Commit your changes using [Conventional Commits](https://www.conventionalcommits.org/) (e.g., `feat: add new feature`, `fix: resolve bug`).
2. Merge your changes to the `main` branch with a PR.
3. The GitHub Action will automatically:
    - Determine the next version number.
    - Update `pyproject.toml` and `src/autodef/__init__.py`.
    - Generate a changelog.
    - Create a GitHub Release with the updated version tag.
    - Build and publish the package to PyPI.

## 🧠 How it Works

1.  **Analysis**: AutoDef inspects function signatures, type hints, and docstrings.
2.  **Prompting**: It constructs a prompt with codebase context, including relevant source code and type definitions.
3.  **Generation**: The LLM generates a robust Python implementation.
4.  **Persistence**: The code is cached in `.autodef_cache/`, giving you full visibility and control over what runs in your environment.

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.
