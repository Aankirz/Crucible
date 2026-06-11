# Crucible Mission Control backend — container image (Render / any host).
#
# Node.js is required because the Phoenix MCP server is launched at runtime via
# `npx @arizeai/phoenix-mcp` (agent-initiated introspection). `uv` manages the
# Python environment and runs the FastAPI app under uvicorn.
FROM python:3.12-slim

# Node.js + npm provide `npx` for the Phoenix MCP server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Pre-install the Phoenix MCP server so the first live introspection doesn't pay
# an npx download cost mid-run.
RUN npm install -g @arizeai/phoenix-mcp@latest

# uv: fast, reproducible Python dependency management.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync

# Copy the application source.
COPY . .

ENV PYTHONUNBUFFERED=1

# The host (Render/Cloud Run) injects $PORT; default to 8080 for local docker run.
# Shell form so ${PORT} is expanded at runtime.
CMD uv run uvicorn crucible.server.app:app --host 0.0.0.0 --port ${PORT:-8080}
