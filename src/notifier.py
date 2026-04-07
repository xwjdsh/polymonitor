from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import telegram
from telegram import InlineKeyboardMarkup

from .config import TelegramConfig

logger = logging.getLogger(__name__)

CallbackHandler = Callable[[Any, str], Awaitable[None]]
CommandHandler = Callable[[Any], Awaitable[None]]


class Notifier:
    """Send notifications via Telegram bot with console fallback."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._bot: telegram.Bot | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._enabled = bool(config.bot_token and config.chat_id)
        self._callback_handlers: list[tuple[str, CallbackHandler]] = []
        self._command_handlers: dict[str, CommandHandler] = {}
        self._poll_offset: int = 0
        self._polling_task: asyncio.Task | None = None
        if self._enabled:
            self._bot = telegram.Bot(token=config.bot_token)
            logger.info("Telegram notifications enabled")
        else:
            logger.warning(
                "Telegram not configured — notifications will only be logged"
            )

    def register_callback_handler(self, prefix: str, handler: CallbackHandler) -> None:
        """Register a handler for callback queries whose data starts with prefix."""
        self._callback_handlers.append((prefix, handler))

    def register_command_handler(self, command: str, handler: CommandHandler) -> None:
        """Register a handler for a Telegram text command (e.g. '/overlap')."""
        self._command_handlers[command] = handler

    async def start_polling(self) -> None:
        """Start background polling for Telegram updates (callback queries)."""
        if self._bot and self._enabled:
            self._polling_task = asyncio.create_task(self._poll_loop())

    async def stop_polling(self) -> None:
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

    async def _poll_loop(self) -> None:
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=self._poll_offset,
                    timeout=10,
                    read_timeout=15,
                )
                for update in updates:
                    self._poll_offset = update.update_id + 1
                    if update.callback_query:
                        await self._dispatch_callback(update.callback_query)
                    elif update.message and update.message.text:
                        await self._dispatch_command(update.message)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Telegram polling error")
                await asyncio.sleep(5)

    async def _dispatch_command(self, message: Any) -> None:
        text = (message.text or "").strip()
        command = text.split()[0].lower()
        # Strip bot username suffix (e.g. /overlap@mybot)
        command = command.split("@")[0]
        handler = self._command_handlers.get(command)
        if handler:
            try:
                await handler(message)
            except Exception:
                logger.exception("Command handler error for %r", command)

    async def _dispatch_callback(self, query: Any) -> None:
        data = query.data or ""
        for prefix, handler in self._callback_handlers:
            if data.startswith(prefix):
                try:
                    await handler(query, data)
                except Exception:
                    logger.exception("Callback handler error for data=%r", data)
                return
        await query.answer()

    async def send(self, message: str) -> None:
        """Send a message. Falls back to logging if Telegram is not configured."""
        logger.info("Notification:\n%s", message)
        if self._bot and self._enabled:
            try:
                await self._bot.send_message(
                    chat_id=self._config.chat_id,
                    text=message,
                    parse_mode="Markdown",
                )
            except Exception:
                logger.exception("Failed to send Telegram message")

    async def send_html(
        self,
        message: str,
        *,
        disable_preview: bool = False,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        """Send an HTML-formatted message."""
        logger.info("Notification:\n%s", message)
        if self._bot and self._enabled:
            try:
                await self._bot.send_message(
                    chat_id=self._config.chat_id,
                    text=message,
                    parse_mode="HTML",
                    disable_web_page_preview=disable_preview,
                    reply_markup=reply_markup,
                )
            except Exception:
                logger.exception("Failed to send Telegram message")
