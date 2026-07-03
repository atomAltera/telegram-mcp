"""Telegram MCP server (read-only).

Exposes a small set of tools that let an AI agent read Telegram channel history
and join channels. The server expects an already-authorized session (created by
`authorize.py`); it never prompts for credentials at runtime, which makes it
safe to run headless inside a container.

Run:
    python server.py            # serves streamable HTTP on MCP_HOST:MCP_PORT
"""

import fcntl
import hashlib
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from client import (
    ChannelInfo,
    MessageInfo,
    build_client,
    primary_username,
    serialize_channel,
    serialize_messages,
)
from telethon.tl.types import Channel, Chat, User

# Hard cap on how many messages a single read can pull, to avoid an agent
# hammering the API (a fast way to get rate-limited or flagged). Override with
# TG_MAX_LIMIT if you know what you're doing.
MAX_MESSAGE_LIMIT = int(os.getenv("TG_MAX_LIMIT", "100"))

# Hard cap on photo size we'll download for get_message_media, in bytes.
# Base64-encoding inflates this by ~33% before it reaches the calling agent.
MAX_MEDIA_BYTES = int(os.getenv("TG_MAX_MEDIA_BYTES", str(15 * 1024 * 1024)))

client = build_client()

# Held open for the whole process so the single-instance lock stays acquired.
_lock_file = None


def _lock_path() -> str:
    """A lock path unique to this session's identity.

    File-based session -> a sidecar next to it; StringSession -> a temp file
    keyed by a hash of the string. Two processes on the same session collide.
    """
    session_string = os.getenv("TG_SESSION_STRING")
    if session_string:
        digest = hashlib.sha256(session_string.encode()).hexdigest()[:16]
        return os.path.join(tempfile.gettempdir(), f"telegram-mcp-{digest}.lock")
    name = os.getenv("TG_SESSION", "telegram-mcp")
    if not name.endswith(".session"):
        name += ".session"
    return name + ".lock"


def _acquire_single_instance_lock() -> None:
    """Refuse to start if another server already owns this session.

    Running two clients against one session risks AUTH_KEY_DUPLICATED, which
    invalidates the session and forces re-authorization.
    """
    global _lock_file
    path = _lock_path()
    _lock_file = open(path, "w")
    try:
        fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        _lock_file.close()
        _lock_file = None
        raise RuntimeError(
            f"Another Telegram MCP instance is already using this session "
            f"(lock held on {path}). Running two clients on one session can get "
            f"the session revoked — refusing to start a second one."
        ) from e
    _lock_file.write(f"{os.getpid()}\n")
    _lock_file.flush()


@asynccontextmanager
async def lifespan(server: FastMCP):
    """Connect the Telegram client for the server's lifetime.

    Fails fast if another instance holds the session lock, or if the session is
    missing/unauthorized, so the operator gets a clear message instead of every
    tool call erroring later (or the session getting revoked).
    """
    _acquire_single_instance_lock()
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError(
            "Telegram session is not authorized. Run `python authorize.py` first "
            "and make sure the session file / TG_SESSION_STRING is provided."
        )
    try:
        yield
    finally:
        await client.disconnect()
        if _lock_file is not None:
            _lock_file.close()


mcp = FastMCP(name="Telegram", lifespan=lifespan)


# --- Helpers ---------------------------------------------------------------

def _normalize_target(channel: str):
    """Turn user-supplied channel reference into something get_entity accepts.

    Accepts @username, https://t.me/... links, or a numeric id.
    """
    channel = channel.strip()
    if channel.lstrip("-").isdigit():
        return int(channel)
    return channel


async def _resolve(channel: str):
    """Resolve a channel reference to a Telethon entity, with clean errors."""
    try:
        return await client.get_entity(_normalize_target(channel))
    except FloodWaitError as e:
        raise ToolError(f"Rate limited by Telegram; retry in {e.seconds}s.") from e
    except (ValueError, TypeError) as e:
        raise ToolError(
            f"Could not resolve channel '{channel}'. Use a public @username, a "
            f"t.me link, or an id of a chat you already have access to."
        ) from e


# --- Tools -----------------------------------------------------------------

@mcp.tool
async def list_channels() -> list[ChannelInfo]:
    """List all channels and groups the account has joined (excludes private chats)."""
    channels: list[ChannelInfo] = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, User):
            continue
        if isinstance(entity, (Channel, Chat)):
            channels.append(serialize_channel(entity))
    return channels


@mcp.tool
async def read_channel_messages(
    channel: str,
    limit: int = 50,
    offset_date: str | None = None,
    min_id: int | None = None,
) -> list[MessageInfo]:
    """Read recent messages from a channel or group, newest first.

    Public channels are read without joining. Use `offset_date` (ISO-8601) or
    `min_id` to page through older/newer history across multiple calls.

    Args:
        channel: @username, t.me link, or numeric id.
        limit: Maximum number of messages to return.
        offset_date: Only return messages older than this ISO-8601 timestamp.
        min_id: Only return messages with id greater than this (for newer pages).
    """
    limit = max(1, min(limit, MAX_MESSAGE_LIMIT))
    entity = await _resolve(channel)
    username = primary_username(entity)

    parsed_date = None
    if offset_date:
        try:
            parsed_date = datetime.fromisoformat(offset_date)
        except ValueError as e:
            raise ToolError(f"Invalid offset_date '{offset_date}': expected ISO-8601.") from e

    raw_messages = []
    try:
        async for message in client.iter_messages(
            entity,
            limit=limit,
            offset_date=parsed_date,
            min_id=min_id or 0,
        ):
            raw_messages.append(message)
    except FloodWaitError as e:
        raise ToolError(f"Rate limited by Telegram; retry in {e.seconds}s.") from e
    return serialize_messages(raw_messages, username)


@mcp.tool
async def get_message_media(channel: str, message_id: int) -> Image:
    """Download a message's photo so a multimodal agent can view/analyze it.

    Only static photos are supported (not videos or generic file attachments).
    For an album (see `read_channel_messages`'s "album x N" media_type), pass
    the id it returned, or any other message id from that album — each photo
    in an album is a distinct, individually downloadable image.

    Args:
        channel: @username, t.me link, or numeric id.
        message_id: The message id, e.g. from read_channel_messages' `id` field.
    """
    entity = await _resolve(channel)
    try:
        message = await client.get_messages(entity, ids=message_id)
    except FloodWaitError as e:
        raise ToolError(f"Rate limited by Telegram; retry in {e.seconds}s.") from e

    if message is None:
        raise ToolError(f"Message {message_id} not found in '{channel}'.")
    if not message.photo:
        raise ToolError(
            f"Message {message_id} in '{channel}' has no photo to download "
            f"(it may be text-only, a video, or another file type)."
        )
    if message.file and message.file.size and message.file.size > MAX_MEDIA_BYTES:
        raise ToolError(
            f"Photo is {message.file.size} bytes, over the {MAX_MEDIA_BYTES}-byte limit."
        )

    try:
        data = await client.download_media(message, file=bytes)
    except FloodWaitError as e:
        raise ToolError(f"Rate limited by Telegram; retry in {e.seconds}s.") from e
    if not data:
        raise ToolError(f"Could not download the photo for message {message_id}.")

    mime_type = message.file.mime_type if message.file else None
    fmt = mime_type.split("/")[-1] if mime_type else "jpeg"
    return Image(data=data, format=fmt)


@mcp.tool
async def join_channel(channel: str) -> ChannelInfo:
    """Join a channel or group so the account can read private/members-only history.

    Not needed to read public channels — use only for private invite links or
    when membership is required.

    Args:
        channel: @username, public t.me link, or a t.me/+HASH invite link.
    """
    ref = channel.strip()
    try:
        # Private invite link: t.me/+HASH or t.me/joinchat/HASH
        if "t.me/+" in ref or "joinchat/" in ref:
            invite_hash = ref.split("+")[-1].split("joinchat/")[-1].rstrip("/")
            updates = await client(ImportChatInviteRequest(invite_hash))
            entity = updates.chats[0]
        else:
            entity = await _resolve(ref)
            await client(JoinChannelRequest(entity))
        return serialize_channel(entity)
    except FloodWaitError as e:
        raise ToolError(f"Rate limited by Telegram; retry in {e.seconds}s.") from e
    except ToolError:
        raise
    except Exception as e:  # surface Telegram errors cleanly
        raise ToolError(f"Failed to join '{channel}': {e}") from e


if __name__ == "__main__":
    mcp.run(
        transport="http",
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("MCP_PORT", "8000")),
    )
