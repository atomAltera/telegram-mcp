import os
import logging
from contextlib import asynccontextmanager
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TG_API_ID = int(os.getenv('API_ID', '0'))
TG_API_HASH = os.getenv('API_HASH', '0')

client = TelegramClient('telegram-mcp', TG_API_ID, TG_API_HASH)


mcp = FastMCP(
    name="Telegram",
)


class PhoneInput(BaseModel):
    """Schema for collecting phone number."""
    phone: str = Field(..., description="Your phone number with country code (e.g., +1234567890)")


class PasswordInput(BaseModel):
    """Schema for collecting 2FA password."""
    password: str = Field(..., description="Your Telegram 2FA password")


class CodeInput(BaseModel):
    """Schema for collecting authentication code."""
    code: str = Field(..., description="The authentication code sent to your Telegram app or SMS")


class ChannelInfo(BaseModel):
    """Information about a Telegram channel or group."""
    chat_id: int = Field(..., description="The unique identifier of the channel/group.")
    chat_name: str = Field(..., description="The name of the channel/group.")
    chat_type: str = Field(..., description="Type: 'channel', 'megagroup', or 'group'.")
    members_count: int | None = Field(None, description="Number of members (if available).")


async def ensure_telegram_client(ctx: Context):
    """
    Ensure the Telegram client is connected and authenticated.

    Does NOT disconnect after use - maintains persistent connection.
    """
    logger.info("Checking Telegram client connection...")

    if not client.is_connected():
        logger.info("Client not connected, connecting now...")
        await client.connect()

    if not await client.is_user_authorized():
        logger.info("Client not authorized, starting authentication flow...")

        # Use elicitation for authentication
        async def phone_callback():
            logger.info("Requesting phone number via elicitation...")
            result = await ctx.elicit(
                message="Please enter your phone number to authenticate with Telegram:",
                response_type=PhoneInput,
            )
            if result.action == "accept" and result.data:
                logger.info(f"Phone number received: {result.data.phone}")
                return result.data.phone
            raise ValueError("Phone number is required for authentication")

        async def password_callback(hint: str = ""):
            logger.info(f"Requesting 2FA password via elicitation (hint: {hint})...")
            message = "Two-factor authentication is enabled. Please enter your password"
            if hint:
                message += f" (hint: {hint})"
            message += ":"

            result = await ctx.elicit(
                message=message,
                response_type=PasswordInput,
            )
            if result.action == "accept" and result.data:
                logger.info("Password received")
                return result.data.password
            raise ValueError("Password is required for 2FA")

        async def code_callback():
            logger.info("Requesting auth code via elicitation...")
            result = await ctx.elicit(
                message="Please enter the authentication code sent to your Telegram app or SMS:",
                response_type=CodeInput,
            )
            if result.action == "accept" and result.data:
                logger.info(f"Auth code received: {result.data.code}")
                return result.data.code
            raise ValueError("Authentication code is required")

        # Start the client with elicitation callbacks
        await client.start(
            phone=phone_callback,
            password=password_callback,
            code_callback=code_callback
        )
        logger.info("Authentication completed successfully")
    else:
        logger.info("Client already authorized")

    return client


@mcp.tool()
async def list_channels(ctx: Context) -> list[ChannelInfo]:
    """
    List all Telegram channels and groups (excluding private chats).

    Returns a list of channels and groups the user is a member of.
    """
    logger.info("list_channels tool called")

    try:
        tg_client = await ensure_telegram_client(ctx)
        logger.info("Client ready, fetching dialogs...")

        channels = []

        async for dialog in tg_client.iter_dialogs():
            entity = dialog.entity

            # Skip private chats (User entities)
            if isinstance(entity, User):
                continue

            # Determine chat type
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
                continue

            # Get chat name
            chat_name = getattr(entity, 'title', 'Unknown')

            # Get members count if available
            members_count = getattr(entity, 'participants_count', None)

            channels.append(ChannelInfo(
                chat_id=entity.id,
                chat_name=chat_name,
                chat_type=chat_type,
                members_count=members_count
            ))

        logger.info(f"Fetched {len(channels)} channels/groups")
        return channels
    except Exception as e:
        logger.error(f"Error in list_channels: {e}", exc_info=True)
        raise
