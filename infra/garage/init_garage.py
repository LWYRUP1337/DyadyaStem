#!/usr/bin/env python3
"""Одноразовая инициализация Garage для разработки. Идемпотентна: можно запускать сколько угодно раз.

Шаги: раскладка узла -> импорт S3-ключа -> бакет -> права ключа -> CORS бакета.
Админ-API Garage v1 вызывается через стандартную библиотеку, CORS выставляется через boto3.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ADMIN_URL = os.environ.get("GARAGE_ADMIN_URL", "http://garage:3903").rstrip("/")
ADMIN_TOKEN = os.environ["GARAGE_ADMIN_TOKEN"]
SCHEME = "https" if os.environ.get("MINIO_SECURE", "false").lower() == "true" else "http"
S3_URL = f"{SCHEME}://{os.environ['MINIO_ENDPOINT']}"
ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
BUCKET = os.environ["MINIO_BUCKET"]
REGION = os.environ.get("S3_REGION", "garage")
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
CAPACITY = int(os.environ.get("GARAGE_CAPACITY_BYTES", "10000000000"))


os.environ.setdefault("AWS_REQUEST_CHECKSUM_CALCULATION", "when_required")
os.environ.setdefault("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_required")


def log(msg):
    print(f"[garage-init] {msg}", flush=True)


def admin(method, path, body=None):
    """Запрос к админ-API. Возвращает (http_status, json_или_текст)."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        ADMIN_URL + path,
        data=data,
        method=method,
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def must(result, what, ok=(200, 204)):
    status, payload = result
    if status not in ok:
        log(f"ОШИБКА: {what}: HTTP {status}: {payload}")
        sys.exit(1)
    return payload


def wait_for_admin():
    for _ in range(60):
        try:
            status, payload = admin("GET", "/v1/status")
            if status == 200:
                return payload
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(1)
    log("ОШИБКА: админ-API Garage не отвечает")
    sys.exit(1)


def ensure_layout(node_id):
    layout = must(admin("GET", "/v1/layout"), "чтение раскладки")
    if layout.get("roles"):
        log("раскладка узла уже есть")
        return
    log("назначаю роль узлу и применяю раскладку")
    must(admin("POST", "/v1/layout",
               [{"id": node_id, "zone": "dc1", "capacity": CAPACITY, "tags": ["dev"]}]),
         "обновление раскладки")
    must(admin("POST", "/v1/layout/apply", {"version": layout.get("version", 0) + 1}),
         "применение раскладки")


def ensure_key():
    status, _ = admin("GET", f"/v1/key?id={ACCESS_KEY}")
    if status == 200:
        log("S3-ключ уже есть")
        return
    log("импортирую S3-ключ")
    must(admin("POST", "/v1/key/import",
               {"accessKeyId": ACCESS_KEY, "secretAccessKey": SECRET_KEY, "name": "dyadyastem"}),
         "импорт ключа")


def ensure_bucket():
    status, payload = admin("GET", f"/v1/bucket?globalAlias={BUCKET}")
    if status == 200:
        log("бакет уже есть")
        return payload["id"]
    log(f"создаю бакет {BUCKET}")
    for _ in range(30):  
        status, payload = admin("POST", "/v1/bucket", {"globalAlias": BUCKET})
        if status == 200:
            return payload["id"]
        time.sleep(2)
    log(f"ОШИБКА: не удалось создать бакет: HTTP {status}: {payload}")
    sys.exit(1)


def ensure_permissions(bucket_id):
    must(admin("POST", "/v1/bucket/allow",
               {"bucketId": bucket_id, "accessKeyId": ACCESS_KEY,
                "permissions": {"read": True, "write": True, "owner": True}}),
         "выдача прав ключу")
    log("права ключа выданы")


def ensure_cors():
    """CORS нужен, чтобы браузер (localhost:5173) мог скачивать дорожки по ссылкам с localhost:3900."""
    try:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=S3_URL,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            region_name=REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        s3.put_bucket_cors(
            Bucket=BUCKET,
            CORSConfiguration={"CORSRules": [{
                "AllowedOrigins": CORS_ORIGINS,
                "AllowedMethods": ["GET", "HEAD"],
                "AllowedHeaders": ["*"],
                "ExposeHeaders": ["ETag", "Content-Length", "Content-Range", "Accept-Ranges"],
                "MaxAgeSeconds": 3600,
            }]},
        )
        log(f"CORS выставлен для: {', '.join(CORS_ORIGINS)}")
    except Exception as e:  # не валим весь запуск, но предупреждаем громко
        log(f"ПРЕДУПРЕЖДЕНИЕ: CORS не выставлен ({e}). Бэкенд заработает, но браузер не сможет скачать дорожки.")


def main():
    status = wait_for_admin()
    node_id = status.get("node")
    if not node_id:
        log(f"ОШИБКА: в ответе /v1/status нет id узла: {status}")
        sys.exit(1)
    ensure_layout(node_id)
    ensure_key()
    bucket_id = ensure_bucket()
    ensure_permissions(bucket_id)
    ensure_cors()
    log("готово: S3 настроен")


if __name__ == "__main__":
    main()
