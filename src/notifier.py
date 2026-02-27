from __future__ import annotations

import asyncio
import logging

import telegram

from .config import TelegramConfig

logger = logging.getLogger(__name__)


class Notifier:
    """Send notifications via Telegram bot with console fallback."""

    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._bot: telegram.Bot | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._enabled = bool(config.bot_token and config.chat_id)
        if self._enabled:
            self._bot = telegram.Bot(token=config.bot_token)
            logger.info("Telegram notifications enabled")
        else:
            logger.warning(
                "Telegram not configured — notifications will only be logged"
            )

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
        self, message: str, *, disable_preview: bool = False
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
                )
            except Exception:
                logger.exception("Failed to send Telegram message")
