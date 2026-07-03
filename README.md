# Telegram MCP Server

A personal, **read-only** [MCP](https://modelcontextprotocol.io) server that lets an AI
agent read Telegram channel/group history and join channels. Built on
[FastMCP](https://gofastmcp.com) + [Telethon](https://docs.telethon.dev).

It does **not** send messages. Authorization is a separate one-time step; the server
runs headless (e.g. in Docker) against an already-authorized session.

## Components

| File           | Role                                                                 |
|----------------|----------------------------------------------------------------------|
| `authorize.py` | One-time interactive login → creates the SQLite session database.    |
| `client.py`    | Shared client factory + message/channel serialization.               |
| `server.py`    | FastMCP server (HTTP transport) exposing the tools.                  |

## Tools

- `list_channels()` — channels/groups the account has joined.
- `read_channel_messages(channel, limit=50, offset_date=None, min_id=None)` — read
  history newest-first. Public channels are read **without joining**. Page with
  `offset_date` (ISO-8601) or `min_id`.
- `join_channel(channel)` — join a public channel or a private invite link.

`channel` accepts a `@username`, a `https://t.me/...` link, or a numeric id.

## Setup

1. Get `API_ID` / `API_HASH` from https://my.telegram.org and export them (an `.envrc`
   works with [direnv](https://direnv.net)):

   ```sh
   export API_ID=...
   export API_HASH=...
   ```

2. Install dependencies:

   ```sh
   make install      # uv sync
   ```

## Authorize (one time)

```sh
make authorize       # uv run python authorize.py
```

Enter phone, login code, and 2FA password when prompted. This writes
`telegram-mcp.session`. Add `--print-string` to also print a portable
`StringSession` (usable via `TG_SESSION_STRING` instead of mounting a file).

## Run locally

```sh
make run             # serves streamable HTTP on http://0.0.0.0:8000/mcp/
```

Point an MCP client at `http://localhost:8000/mcp/`.

## Run in Docker

For local testing, `docker-compose.yml` (not committed — host-specific) builds and runs the
image with the session file mounted and API credentials passed as env vars:

```sh
API_ID=... API_HASH=... docker compose up --build
```

## Publish the image

```sh
make build            # docker build -t atomaltera/telegram-mcp:latest .  (local arch, fast inner loop)
make push             # multi-arch (linux/amd64+arm64) buildx build --push
```

`push` always builds both architectures via `buildx`, regardless of which arch you're
publishing from — deployment targets are often a different CPU arch than your dev machine,
and a plain `docker build && docker push` would silently overwrite the multi-arch manifest
with a single-arch one. Override `IMAGE`/`TAG`/`PLATFORMS` to publish elsewhere, e.g.
`make push IMAGE=myuser/telegram-mcp`.

## Deploy

Production deployment (pulling the published image, mounting the session with uid-1000
permissions, joining a dedicated Docker network) is managed outside this repo via Ansible.

## Configuration (environment)

| Variable            | Default          | Purpose                                            |
|---------------------|------------------|----------------------------------------------------|
| `API_ID`            | —                | Telegram API id (required).                        |
| `API_HASH`          | —                | Telegram API hash (required).                      |
| `TG_SESSION`        | `telegram-mcp`   | SQLite session name/path.                          |
| `TG_SESSION_STRING` | —                | If set, use an in-memory StringSession (no file).  |
| `MCP_HOST`          | `0.0.0.0`        | Bind host.                                         |
| `MCP_PORT`          | `8000`           | Bind port.                                         |
| `TG_MAX_LIMIT`      | `100`            | Max messages a single read may return.             |

## ⚠️ One session, one instance

Do **not** run two servers against the **same** session at once (e.g. locally *and* on the
remote host). Two clients sharing one session can trigger Telegram's `AUTH_KEY_DUPLICATED`,
which revokes the session. The server guards against this with a startup file lock and refuses
to start a second instance on the same session — but the safest rule is one authorized session
per host. Keep reads modest (`TG_MAX_LIMIT`) and avoid rapid mass-joins to stay clear of bans.

## Example use case

Give an agent a list of news channels and ask it to summarize what's happening: for each
channel it calls `read_channel_messages("@channel", limit=30)`, then analyzes the returned
text/dates/view counts. No membership required for public channels.
