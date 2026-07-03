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

The session file is mounted into the container; API credentials are passed as env vars.
From a host that already has `telegram-mcp.session`:

```sh
API_ID=... API_HASH=... make up      # docker compose up
```

## Configuration (environment)

| Variable            | Default          | Purpose                                            |
|---------------------|------------------|----------------------------------------------------|
| `API_ID`            | —                | Telegram API id (required).                        |
| `API_HASH`          | —                | Telegram API hash (required).                      |
| `TG_SESSION`        | `telegram-mcp`   | SQLite session name/path.                          |
| `TG_SESSION_STRING` | —                | If set, use an in-memory StringSession (no file).  |
| `MCP_HOST`          | `0.0.0.0`        | Bind host.                                         |
| `MCP_PORT`          | `8000`           | Bind port.                                         |

## Example use case

Give an agent a list of news channels and ask it to summarize what's happening: for each
channel it calls `read_channel_messages("@channel", limit=30)`, then analyzes the returned
text/dates/view counts. No membership required for public channels.
