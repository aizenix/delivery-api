import httpx
from celery import Celery

from app.config import settings
from app.sms import get_sms_client

celery_app = Celery("delivery", broker=settings.celery_broker_url)
celery_app.conf.update(
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
)


@celery_app.task(autoretry_for=(httpx.HTTPError,), retry_backoff=True, max_retries=3)
def send_sms(phone: str, text: str) -> None:
    get_sms_client().send(phone, text)
