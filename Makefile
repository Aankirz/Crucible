setup:
	uv sync

test:
	uv run pytest -q

spike:
	uv run python scripts/spike_adk_phoenix_mcp.py

serve:
	uv run uvicorn crucible.server.app:app --reload --port 8000

.PHONY: setup test spike serve
