.PHONY: install authorize run build push shell clean

IMAGE ?= atomaltera/telegram-mcp
TAG ?= latest

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
	docker build -t $(IMAGE):$(TAG) .

# Publish the Docker image to Docker Hub.
push: build
	docker push $(IMAGE):$(TAG)

# Open a shell in the built image for debugging.
shell:
	docker run --rm -it --entrypoint sh $(IMAGE):$(TAG)

# Remove the Docker image.
clean:
	docker image rm $(IMAGE):$(TAG) || true
