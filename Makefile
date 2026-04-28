.PHONY: run setup

setup:
	uv venv && uv pip install -e "."

run:
	uv run python -m src.main
