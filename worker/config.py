import os


def _bool(name: str, default: str) -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


DATABASE_URL_SYNC = os.environ["DATABASE_URL_SYNC"]

MINIO_ENDPOINT = os.environ["MINIO_ENDPOINT"] # garage:3900
MINIO_ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
MINIO_SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
MINIO_BUCKET = os.environ["MINIO_BUCKET"]
MINIO_SECURE = _bool("MINIO_SECURE", "false")
S3_REGION = os.getenv("S3_REGION", "garage")


MAX_DURATION_SEC = int(os.getenv("MAX_DURATION_SEC", "600"))


DEMUCS_SEGMENT = os.getenv("DEMUCS_SEGMENT", "6")
DEMUCS_DEVICE = os.getenv("DEMUCS_DEVICE", "cpu")
DEMUCS_TIMEOUT_SEC = int(os.getenv("DEMUCS_TIMEOUT_SEC", "1800"))
WORK_DIR = os.getenv("WORK_DIR", "/tmp/dyadyastem")
