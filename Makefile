.PHONY: install authorize run build up down shell clean

# Install dependencies into the local .venv via uv.
install:
	uv sync

# One-time interactive login on the host; creates telegram-mcp.session.
authorize:
	uv run python authorize.py

# Run the MCP server locally (HTTP on MCP_PORT, default 8000).
run:
	uv run python server.py

# Build the Docker image.
build:
	docker compose build

# Run the containerized server (requires API_ID, API_HASH and a session file).
up:
	docker compose up

down:
	docker compose down

# Open a shell in the built image for debugging.
shell:
	docker compose run --rm --entrypoint sh telegram-mcp

# Remove the Docker image.
clean:
	docker image rm telegram-mcp || true
