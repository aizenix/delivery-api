import logging
from typing import Protocol

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SMSClient(Protocol):
    def send(self, phone: str, text: str) -> None: ...


class ConsoleSMS:
    def send(self, phone: str, text: str) -> None:
        logger.info("sms to %s: %s", phone, text)


class HttpSMS:
    """Generic JSON gateway: POST {phone, text, sender} with a bearer token.

    Field names differ between providers (Eskiz, Playmobile and others), so switching
    gateways usually means adjusting the payload here and nothing else.
    """

    def __init__(self, url: str, token: str, sender: str, client: httpx.Client | None = None):
        self.url = url
        self.token = token
        self.sender = sender
        self.client = client or httpx.Client(timeout=10)

    def send(self, phone: str, text: str) -> None:
        response = self.client.post(
            self.url,
            json={"phone": phone.lstrip("+"), "text": text, "sender": self.sender},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        response.raise_for_status()


def get_sms_client() -> SMSClient:
    if settings.sms_backend == "http":
        return HttpSMS(settings.sms_gateway_url, settings.sms_gateway_token, settings.sms_sender)
    return ConsoleSMS()
