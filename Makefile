.PHONY: install authorize run build push shell clean

IMAGE ?= atomaltera/telegram-mcp
TAG ?= latest
PLATFORMS ?= linux/amd64,linux/arm64

# Install dependencies into the local .venv via uv.
install:
	uv sync

# One-time interactive login on the host; creates telegram-mcp.session.
authorize:
	uv run python authorize.py

# Run the MCP server locally (HTTP on MCP_PORT, default 8000).
run:
	uv run python server.py

# Build the Docker image for the local architecture only (fast inner loop,
# not for publishing — deployment targets may be a different arch).
build:
	docker build -t $(IMAGE):$(TAG) .

# Publish a multi-arch manifest (linux/amd64 + linux/arm64) to Docker Hub.
# Deliberately NOT `build`+`docker push`: that only pushes the local arch and
# silently overwrites any existing multi-arch manifest with a single-arch one.
push:
	docker buildx build --platform $(PLATFORMS) -t $(IMAGE):$(TAG) --push .

# Open a shell in the built image for debugging.
shell:
	docker run --rm -it --entrypoint sh $(IMAGE):$(TAG)

# Remove the Docker image.
clean:
	docker image rm $(IMAGE):$(TAG) || true
