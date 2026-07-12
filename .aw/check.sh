#!/bin/bash
set -e

# Run standard checks
echo "Running Ruff (linting)..."
uv run ruff check .

echo "Running Mypy (type checking)..."
uv run mypy .

echo "Running Pytest (tests)..."
uv run pytest

echo "All checks passed! 🎉"
