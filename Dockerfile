# Telegram MCP server — read-only, HTTP transport.
FROM python:3.13-slim

# uv for fast, reproducible installs from the lockfile.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Application code.
COPY client.py server.py authorize.py ./

# Run as a fixed non-root uid so a host-mounted session file owned by uid 1000
# is readable/writable by the process (Telethon's SQLite session gets written
# to during normal operation).
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    TG_SESSION=/data/telegram-mcp

EXPOSE 8000

# The session database is mounted at /data (see docker-compose.yml).
CMD ["uv", "run", "--no-dev", "python", "server.py"]
