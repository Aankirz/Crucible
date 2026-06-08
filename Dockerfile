# Crucible Mission Control backend — Cloud Run image (plan Task 8.2).
#
# Node.js is required because the Phoenix MCP server is launched at runtime via
# `npx @arizeai/phoenix-mcp` (agent-initiated introspection). `uv` manages the
# Python environment and runs the FastAPI app under uvicorn.
FROM python:3.11-slim

# Node.js + npm provide `npx` for the Phoenix MCP server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# uv: fast, reproducible Python dependency management.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY uv.lock* ./
RUN uv sync

# Copy the application source.
COPY . .

# Cloud Run injects PORT; default to 8080 for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "crucible.server.app:app", \
     "--host", "0.0.0.0", "--port", "8080"]
