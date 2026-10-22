import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def send_message(chat_id: int, text: str) -> None:
    if not settings.telegram_bot_token:
        logger.info("telegram token not set, message to %s: %s", chat_id, text)
        return
    response = httpx.post(
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
