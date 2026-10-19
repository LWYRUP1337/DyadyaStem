import shutil
import uuid
from pathlib import Path

from celery.utils.log import get_task_logger
from mutagen import MutagenError
from mutagen.mp3 import MP3

import config
import repo
import s3
from cel import app
from demucs_runner import ProcessingError, separate

log = get_task_logger(__name__)


@app.task(name="process_audio")
def process_audio(project_id: str) -> None:
    try:
        pid = uuid.UUID(project_id)
    except ValueError:
        log.error("process_audio: некорректный project_id=%r", project_id)
        return

    project = repo.get_project(pid)
    if project is None:
        log.error("process_audio: проект %s не найден", project_id)
        return
    if project["status"] != "processing":
        # дубль задачи (например, повторная доставка) или проект уже обработан
        log.warning("process_audio: проект %s в статусе %s, пропускаю", project_id, project["status"])
        return

    log.info("process_audio: старт, проект %s, модель %s", project_id, project["model"])
    work_dir = Path(config.WORK_DIR) / project_id
    try:
        _cleanup_previous(pid, project_id)
        input_path = _fetch_source(project, work_dir)
        duration_sec = _check_mp3(input_path)
        stems = separate(input_path, work_dir / "out", project["model"])
        stem_keys = _upload_stems(project_id, stems)
        repo.mark_ready(pid, duration_sec, stem_keys)
        log.info("process_audio: готово, проект %s (%s дорожек, %s с)", project_id, len(stem_keys), duration_sec)
    except ProcessingError as e:
        log.error("process_audio: проект %s: %s", project_id, e)
        _fail(pid, project_id, str(e))
    except Exception:
        log.exception("process_audio: непредвиденная ошибка, проект %s", project_id)
        _fail(pid, project_id, "Внутренняя ошибка при обработке трека")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _cleanup_previous(pid: uuid.UUID, project_id: str) -> None:
    repo.clear_tracks(pid)
    s3.delete_prefix(f"stems/{project_id}/")


def _fetch_source(project: dict, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    dest = work_dir / "input.mp3"
    if project["source_file_key"]:
        s3.download(project["source_file_key"], dest)
        return dest
    if project["source_url"]:
        # TODO скачивание по ссылке с защитой от SSRF
        raise ProcessingError("Загрузка по ссылке пока не поддерживается")
    raise ProcessingError("У проекта нет исходного файла")


def _check_mp3(path: Path) -> int:
    """Проверяет, что это mp3 допустимой длины. Возвращает длительность в секундах."""
    try:
        length = MP3(str(path)).info.length
    except MutagenError:
        raise ProcessingError("Файл не распознан как mp3 или повреждён")
    if length > config.MAX_DURATION_SEC:
        raise ProcessingError(f"Трек длиннее {config.MAX_DURATION_SEC // 60} минут")
    return max(1, round(length))


def _upload_stems(project_id: str, stems: dict[str, Path]) -> dict[str, str]:
    keys = {}
    for stem, path in stems.items():
        key = f"stems/{project_id}/{stem}.mp3"
        s3.upload(path, key)
        keys[stem] = key
    return keys


def _fail(pid: uuid.UUID, project_id: str, message: str) -> None:
    """Записывает ошибку. Сама никогда не бросает исключений: падать здесь уже некуда."""
    try:
        s3.delete_prefix(f"stems/{project_id}/")
    except Exception:
        log.warning("не удалось очистить стемы проекта %s", project_id, exc_info=True)
    try:
        repo.mark_error(pid, message)
    except Exception:
        log.exception("не удалось записать ошибку в БД, проект %s", project_id)
