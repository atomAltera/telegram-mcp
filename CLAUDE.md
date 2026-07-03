# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A personal, **read-only** Telegram MCP (Model Context Protocol) server built with FastMCP
and Telethon. It lets AI agents read Telegram channel/group history and join channels. It
does **not** send messages.

Authorization is a **separate one-time step** (`authorize.py`) that produces a session
database. The server (`server.py`) runs headless against that session and never prompts for
credentials — it is designed to run inside a Docker container in a trusted perimeter.

**Key dependencies** (see `pyproject.toml`):
- `fastmcp>=2.13.0.2` — MCP server framework
- `telethon>=1.42.0` — Telegram client library
- Python 3.13+

**Required environment variables:**
- `API_ID`, `API_HASH` — from https://my.telegram.org

## Architecture

Three source files (flat layout):

- **`client.py`** — shared. `build_client()` constructs a `TelegramClient` from env
  (SQLite session via `TG_SESSION`, or an in-memory `StringSession` via
  `TG_SESSION_STRING`). Pydantic response models `ChannelInfo` / `MessageInfo` and the
  `serialize_channel` / `serialize_message` helpers live here. Connecting and authorizing
  are the caller's responsibility.

- **`authorize.py`** — standalone CLI. Calls `TelegramClient.start()`, which interactively
  prompts (on the terminal) for phone, login code, and 2FA password, then writes the
  session file. Nothing sensitive is logged. `--print-string` also prints a portable
  StringSession.

- **`server.py`** — the MCP server. A module-level `client = build_client()` is connected
  once for the process lifetime via a FastMCP **lifespan** context manager; if the session
  is not authorized the server fails fast with a clear message. Tools use this persistent
  client directly (no per-call connect/disconnect, no elicitation). Served over **HTTP**
  (`mcp.run(transport="http", ...)`) so a remote agent can reach it.

### Transport
HTTP (streamable-http) on `MCP_HOST:MCP_PORT` (default `0.0.0.0:8000`, path `/mcp/`). This
is required for the "container on a remote host, external agent" deployment; stdio would
only work same-host.

## Tools (all read-only)

Defined with the `@mcp.tool` decorator on async functions in `server.py`:

- `list_channels()` → `list[ChannelInfo]` — joined channels/groups (skips `User` chats).
- `read_channel_messages(channel, limit=50, offset_date=None, min_id=None)` →
  `list[MessageInfo]` — resolves `channel` (public channels need no join) and iterates
  history newest-first. Paging via `offset_date` (ISO-8601) / `min_id`.
- `join_channel(channel)` → `ChannelInfo` — `JoinChannelRequest` for public refs,
  `ImportChatInviteRequest` for `t.me/+`/`joinchat/` invite links.

`channel` may be a `@username`, a `t.me` link, or a numeric id (`_normalize_target` /
`_resolve` in `server.py`). `FloodWaitError` and resolution failures are surfaced as
`fastmcp.exceptions.ToolError` with actionable messages.

## Development Commands

`Makefile` targets:

```bash
make install     # uv sync
make authorize   # one-time interactive login -> telegram-mcp.session
make run         # run server locally (HTTP :8000)
make build       # docker build -t $(IMAGE):$(TAG) .  local arch only (IMAGE ?= atomaltera/telegram-mcp, TAG ?= latest)
make push        # multi-arch buildx build --platform $(PLATFORMS) --push (PLATFORMS ?= linux/amd64,linux/arm64)
make shell       # shell into the built image
make clean       # remove the local image
```

For local container testing there's also `docker-compose.yml` (not committed — host-specific
volumes/ports), used directly via `docker compose up --build`, not through the Makefile.

## Docker

`Dockerfile` (uv, python:3.13-slim) installs from `uv.lock`, copies the app, then adds a
fixed non-root user (`useradd --uid 1000 ... && USER appuser`) so a host-mounted session
file owned by uid 1000 is readable/writable by the process. Runs `server.py`.

The image is published to Docker Hub as `atomaltera/telegram-mcp`, always multi-arch
(`linux/amd64` + `linux/arm64`) via `make push` (buildx). **Never** publish with a plain
`docker build && docker push` — it only builds the local arch and silently overwrites the
existing multi-arch manifest with a single-arch one, breaking `docker compose pull` on any
other architecture. This actually happened once (deploy failed with `no matching manifest
for linux/amd64/v3`); the Makefile's `push` target now always goes through buildx to make
that mistake structurally impossible.

Production deployment (pulling the image, mounting the session at
`/data/telegram-mcp.session` with uid-1000 permissions, joining a dedicated Docker network
so other services can reach `http://telegram-mcp:8000/mcp/`) is managed outside this repo,
via Ansible.

## Single instance & ban safety

**One session = one running process.** Two Telegram clients connected with the same session
simultaneously can trigger `AUTH_KEY_DUPLICATED`, which **revokes the session** and forces
re-authorization. To prevent this, `server.py` takes a non-blocking `fcntl.flock` at startup
(`_acquire_single_instance_lock`, sidecar `<session>.lock`, held for the process lifetime); a
second instance on the same session **fails fast** instead of starting. Do not run the server
locally and on the remote host against the *same* session at the same time — give each host its
own authorized session, or run only one.

Other ban-avoidance measures baked in:
- `read_channel_messages` clamps `limit` to `MAX_MESSAGE_LIMIT` (env `TG_MAX_LIMIT`, default 100)
  so an agent can't hammer the API with huge history pulls.
- Joining is a separate, explicit tool (never automatic) — mass/rapid joins are a classic
  ban trigger.
- `FloodWaitError` is surfaced (not swallowed) so the agent backs off.

## Important Notes

- **Never add elicitation/auth to `server.py`.** The server assumes an authorized session;
  authorization belongs to `authorize.py`.
- **Read-only.** Do not add message-sending tools without an explicit decision — writing is
  intentionally out of scope for now.
- **Secrets** (`.envrc`, `*.session`) are gitignored; keep them out of the repo and out of
  logs.
- **Adding tools:** decorate an async function with `@mcp.tool` in `server.py`, use the
  module-level `client`, resolve channel references with `_resolve`, and return Pydantic
  models from `client.py`. Wrap Telegram errors in `ToolError`.
- **Session reuse:** `TG_SESSION` defaults to `telegram-mcp`, matching the existing
  `telegram-mcp.session`, so re-auth isn't needed if that file is valid.
