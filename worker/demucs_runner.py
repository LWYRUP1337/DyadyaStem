import logging
import subprocess
import sys
from pathlib import Path

import config

log = logging.getLogger(__name__)


STEMS_BY_MODEL = {
    "htdemucs": ["vocals", "drums", "bass", "other"],
    "htdemucs_6s": ["vocals", "drums", "bass", "other", "guitar", "piano"],
}

NETWORK_ERROR_MARKERS = ("urlopen error", "HTTP Error", "Connection", "Name or service not known")


class ProcessingError(Exception):
    """Ошибка, текст которой безопасно показать пользователю (попадает в projects.error_message)."""


def separate(input_path: Path, out_dir: Path, model: str) -> dict[str, Path]:
    """Разделяет трек. Возвращает {тип_дорожки: путь_к_mp3}."""
    if model not in STEMS_BY_MODEL:
        raise ProcessingError("Неизвестная модель разделения")

    cmd = [
        sys.executable, "-m", "demucs.separate",
        "-n", model,
        "-d", config.DEMUCS_DEVICE,
        "--mp3", "--mp3-bitrate", "320",
        "-o", str(out_dir),
    ]
    if config.DEMUCS_SEGMENT:
        cmd += ["--segment", str(config.DEMUCS_SEGMENT)]
    cmd.append(str(input_path))

    log.info("запускаю Demucs: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            timeout=config.DEMUCS_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        raise ProcessingError("Обработка заняла слишком много времени и была остановлена")

    if proc.returncode != 0:
        tail = (proc.stderr or "")[-1500:]
        log.error("Demucs завершился с кодом %s:\n%s", proc.returncode, tail)
        if proc.returncode in (-9, 137):
            raise ProcessingError("Не хватило памяти для обработки трека. Попробуйте трек покороче")
        if any(marker in tail for marker in NETWORK_ERROR_MARKERS):
            raise ProcessingError("Модель разделения недоступна: веса не скачаны")
        raise ProcessingError("Не удалось разделить трек на дорожки")

    track_dir = out_dir / model / input_path.stem
    result: dict[str, Path] = {}
    for stem in STEMS_BY_MODEL[model]:
        path = track_dir / f"{stem}.mp3"
        if not path.is_file():
            log.error("после Demucs нет файла %s", path)
            raise ProcessingError("Не удалось разделить трек на дорожки")
        result[stem] = path
    return result
