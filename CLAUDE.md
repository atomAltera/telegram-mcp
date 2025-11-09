# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram MCP (Model Context Protocol) server built with FastMCP and Python. The server provides read-only access to Telegram channels and groups, allowing AI assistants to list and interact with the user's Telegram data.

**Key Dependencies:**
- `mcp[cli]>=1.21.0` - Model Context Protocol SDK
- `telethon>=1.42.0` - Telegram client library for API access
- Python 3.13+

**Environment Variables Required:**
- `API_ID` - Telegram API ID (obtain from https://my.telegram.org)
- `API_HASH` - Telegram API Hash (obtain from https://my.telegram.org)

## Architecture

The project uses **FastMCP**, a high-level Python framework for building MCP servers, combined with **Telethon** for Telegram API access. Key architectural patterns:

1. **Server Initialization**: The MCP server is created as a singleton instance (`mcp = FastMCP(name="Telegram", ...)`) at module level in main.py:15-18

2. **Telegram Client**: A persistent TelegramClient instance is created at module level (main.py:13) using credentials from environment variables. The client lifecycle is managed through an async context manager.

3. **Async Context Manager**: The `get_telegram_client()` context manager (main.py:45-93) handles the complete client lifecycle:
   - Connects to Telegram on entry
   - Checks authorization and triggers authentication if needed
   - Yields the connected client for use
   - Guarantees disconnection on exit (via `finally` block)

   This ensures proper resource cleanup and prevents connection leaks.

4. **Elicitation-Based Authentication**: Instead of requiring credentials upfront, the server uses MCP's elicitation feature to interactively request authentication information within the context manager:
   - Phone number (main.py:57-64)
   - 2FA password if enabled (main.py:66-73)
   - Authentication code from SMS/Telegram app (main.py:75-82)

   This allows the MCP client to prompt users in real-time during the authentication flow.

5. **Tool Pattern**: Tools are defined using the `@mcp.tool()` decorator on async functions. Tools can accept a `ctx: Context[ServerSession, None]` parameter for accessing elicitation. The server currently exposes: `list_channels` (main.py:96-139)

6. **Structured Data with Pydantic**: Both input schemas for elicitation (e.g., `PhoneInput` at main.py:22-24) and response schemas (e.g., `ChannelInfo` at main.py:37-42) are defined using Pydantic models to ensure type-safe, well-documented interactions

7. **Entity Type Filtering**: The server filters Telegram entities by type using `isinstance()` checks to distinguish between User (private chats), Channel (channels/megagroups), and Chat (basic groups) entities

## Development Commands

### Running the MCP Server

The project uses `uv` for dependency management. To run the server, use the FastMCP CLI:

```bash
# Run with fastmcp CLI
fastmcp run main.py:mcp

# Or with uv
uv run fastmcp run main.py:mcp
```

The format is `module_path:mcp_instance_name` where `mcp` is the FastMCP instance defined in main.py:6.

MCP servers typically communicate over stdio and are meant to be integrated with MCP clients (like Claude Desktop or other AI assistants) rather than run directly.

### Installing Dependencies

```bash
uv sync
```

### Working with the Virtual Environment

The project uses a `.venv` directory for the virtual environment managed by `uv`.

### Docker Commands

The project includes Docker support via Makefile. You must provide Telegram API credentials as environment variables:

```bash
# Build the Docker image
make build

# Run the containerized server (requires API_ID and API_HASH)
API_ID=your_api_id API_HASH=your_api_hash make run

# The Makefile automatically:
# - Passes API_ID and API_HASH to the container
# - Mounts the session file (telegram-mcp.session) for persistence

# Open a shell in the container (for debugging)
make shell

# Remove the Docker image
make clean
```

## Current Implementation

The server currently implements one tool:

**`list_channels(ctx: Context[ServerSession, None])`** - Lists all Telegram channels and groups (excluding private chats)
- Uses the `get_telegram_client()` context manager (main.py:103) to handle client lifecycle
- The context manager connects to Telegram and handles authentication via elicitation if needed:
  - Phone number via `PhoneInput` schema
  - 2FA password via `PasswordInput` schema (only if 2FA is enabled)
  - Authentication code via `CodeInput` schema
- Iterates through all dialogs using `client.iter_dialogs()`
- Filters out User entities (private chats) at main.py:110-111
- Distinguishes between channels (broadcast), megagroups, and regular groups
- Returns a list of `ChannelInfo` objects with chat_id, chat_name, chat_type, and members_count
- Client automatically disconnects when the context manager exits

## Important Notes

- **Authentication Flow**: The server uses MCP elicitation for interactive authentication. On first run (or when session expires), the MCP client will prompt users for:
  1. Phone number (with country code)
  2. Authentication code (sent to Telegram app or SMS)
  3. 2FA password (only if enabled on the account)
- **Session Persistence**: After successful authentication, credentials are saved to `telegram-mcp.session` for future use
- **Environment Variables**: Set `API_ID` and `API_HASH` before running (obtain from https://my.telegram.org)
- **Adding Tools**: Use the `@mcp.tool()` decorator on async functions. Include `ctx: Context[ServerSession, None]` parameter if you need elicitation. Use the `get_telegram_client(ctx)` context manager to ensure proper connection lifecycle management
- **Pydantic Schemas**: Define Pydantic models for both elicitation inputs and tool outputs to ensure type-safe MCP serialization
- **Client Lifecycle**: Always use the `get_telegram_client()` async context manager when accessing the Telegram client to ensure proper connection/disconnection
