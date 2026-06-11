# Crucible Mission Control — single-service image (API + UI) for Render / any host.
#
# Stage 1 builds the Vite UI; stage 2 runs FastAPI (which serves both the API and
# the built UI at the same origin). Node.js is also needed at runtime because the
# Phoenix MCP server is launched via `npx @arizeai/phoenix-mcp`.

# --- Stage 1: build the React/Vite UI ----------------------------------------
FROM node:22-slim AS ui-build
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
# Empty API base -> the UI calls the same origin that serves it (/events, /run).
ENV VITE_API_URL=""
RUN npm run build

# --- Stage 2: Python runtime (API + static UI) -------------------------------
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

# Bring in the built UI from stage 1 and tell the app where to serve it from.
COPY --from=ui-build /ui/dist ./ui_dist
ENV CRUCIBLE_UI_DIST=/app/ui_dist

ENV PYTHONUNBUFFERED=1

# The host (Render/Cloud Run) injects $PORT; default to 8080 for local docker run.
# Shell form so ${PORT} is expanded at runtime.
CMD uv run uvicorn crucible.server.app:app --host 0.0.0.0 --port ${PORT:-8080}
