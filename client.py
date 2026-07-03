"""Shared Telegram client construction and serialization helpers.

Used by both the authorization script (`authorize.py`) and the MCP server
(`server.py`). Reads configuration from environment variables so the same code
runs identically locally and inside the Docker container.
"""

import os

from pydantic import BaseModel, Field
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.custom import Message
from telethon.tl.types import Channel, Chat, User


# --- Configuration ---------------------------------------------------------

def _api_credentials() -> tuple[int, str]:
    """Read and validate Telegram API credentials from the environment."""
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    if not api_id or not api_hash:
        raise RuntimeError(
            "API_ID and API_HASH must be set (obtain them from https://my.telegram.org)."
        )
    return int(api_id), api_hash


def build_client() -> TelegramClient:
    """Construct a TelegramClient from environment configuration.

    Session storage is chosen by env:
      - TG_SESSION_STRING : if set, an in-memory StringSession (portable, no file).
      - TG_SESSION        : otherwise, name/path of the SQLite session file
                            (default "telegram-mcp", producing telegram-mcp.session).

    Connecting and authorization are the caller's responsibility.
    """
    api_id, api_hash = _api_credentials()

    session_string = os.getenv("TG_SESSION_STRING")
    if session_string:
        session = StringSession(session_string)
    else:
        session = os.getenv("TG_SESSION", "telegram-mcp")

    return TelegramClient(session, api_id, api_hash)


# --- Response schemas ------------------------------------------------------

class ChannelInfo(BaseModel):
    """Information about a Telegram channel or group."""
    chat_id: int = Field(..., description="The unique identifier of the channel/group.")
    chat_name: str = Field(..., description="The name/title of the channel/group.")
    chat_type: str = Field(..., description="Type: 'channel', 'megagroup', or 'group'.")
    username: str | None = Field(None, description="Public @username, if any.")
    members_count: int | None = Field(None, description="Number of members, if available.")


class MessageInfo(BaseModel):
    """A single message fetched from a channel or group."""
    id: int = Field(..., description="Message id within the channel.")
    date: str | None = Field(None, description="ISO-8601 timestamp of the message.")
    text: str = Field("", description="Message text (may be empty for media-only posts).")
    sender_name: str | None = Field(None, description="Display name of the author, if known.")
    views: int | None = Field(None, description="View count, for broadcast channels.")
    forwards: int | None = Field(None, description="Forward count, if available.")
    reply_to_msg_id: int | None = Field(None, description="Id of the message this replies to.")
    has_media: bool = Field(False, description="Whether the message carries media.")
    media_type: str | None = Field(None, description="Media class name, e.g. 'MessageMediaPhoto'.")
    url: str | None = Field(None, description="Public t.me link to the message, if resolvable.")


# --- Serialization ---------------------------------------------------------

def primary_username(entity) -> str | None:
    """Return an entity's public @username.

    Handles both the legacy single `username` field and the newer collectible
    `usernames` list (where the active handle carries `.active = True`).
    """
    username = getattr(entity, "username", None)
    if username:
        return username
    usernames = getattr(entity, "usernames", None) or []
    for u in usernames:
        if getattr(u, "active", False):
            return u.username
    return usernames[0].username if usernames else None


def serialize_channel(entity) -> ChannelInfo:
    """Turn a Telethon Channel/Chat entity into a ChannelInfo."""
    if isinstance(entity, Channel):
        if entity.broadcast:
            chat_type = "channel"
        elif entity.megagroup:
            chat_type = "megagroup"
        else:
            chat_type = "group"
    elif isinstance(entity, Chat):
        chat_type = "group"
    else:
        chat_type = "unknown"

    return ChannelInfo(
        chat_id=entity.id,
        chat_name=getattr(entity, "title", None) or "Unknown",
        chat_type=chat_type,
        username=primary_username(entity),
        members_count=getattr(entity, "participants_count", None),
    )


def _sender_name(message: Message) -> str | None:
    """Best-effort human-readable author name for a message."""
    sender = message.sender
    if isinstance(sender, User):
        parts = [p for p in (sender.first_name, sender.last_name) if p]
        if parts:
            return " ".join(parts)
        if sender.username:
            return sender.username
    if isinstance(sender, (Channel, Chat)):
        return getattr(sender, "title", None)
    # Channel posts often have no sender entity; fall back to signed author.
    return getattr(message, "post_author", None)


def serialize_message(message: Message, channel_username: str | None) -> MessageInfo:
    """Turn a Telethon Message into a MessageInfo."""
    media = message.media
    url = None
    if channel_username:
        url = f"https://t.me/{channel_username}/{message.id}"

    return MessageInfo(
        id=message.id,
        date=message.date.isoformat() if message.date else None,
        text=message.message or "",
        sender_name=_sender_name(message),
        views=getattr(message, "views", None),
        forwards=getattr(message, "forwards", None),
        reply_to_msg_id=message.reply_to_msg_id,
        has_media=media is not None,
        media_type=type(media).__name__ if media is not None else None,
        url=url,
    )
