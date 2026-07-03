"""Interactive Telegram authorization.

Run this ONCE locally to create the session database that the MCP server reads.
The server itself never authenticates — it expects an already-authorized session.

Usage:
    python authorize.py

Environment:
    API_ID, API_HASH     required (https://my.telegram.org)
    TG_SESSION           session file name/path (default "telegram-mcp")

On success a SQLite file (e.g. telegram-mcp.session) is written next to this
script. Mount that file into the container. To instead print a portable
StringSession (for the TG_SESSION_STRING env var), pass --print-string.
"""

import asyncio
import os
import sys

from telethon.sessions import StringSession

from client import build_client


async def main() -> int:
    print_string = "--print-string" in sys.argv

    client = build_client()
    # `start()` interactively prompts on the terminal for phone, login code,
    # and 2FA password as needed. Nothing sensitive is logged.
    await client.start()

    me = await client.get_me()
    name = " ".join(p for p in (me.first_name, me.last_name) if p) or me.username
    print(f"\n✓ Authorized as {name} (id={me.id}).")

    session_name = os.getenv("TG_SESSION", "telegram-mcp")
    print(f"  Session saved to: {session_name}.session")

    if print_string:
        string = StringSession.save(client.session)
        print("\nStringSession (set as TG_SESSION_STRING to avoid mounting a file):")
        print(string)

    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
