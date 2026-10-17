
from celery.utils.log import get_task_logger

from cel import app

log = get_task_logger(__name__)


@app.task(name="process_audio")
def process_audio(project_id: str) -> None:
    log.info("process_audio получил project_id=%s (заглушка, Demucs ещё не подключён)", project_id)
