import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

app = Celery(
    "dyadyastem_worker",
    broker=REDIS_URL,
    include=["tasks.process_audio"],
)

app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    timezone="UTC",
)
