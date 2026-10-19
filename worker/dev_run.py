"""Помощник для разработки: прогоняет process_audio без бэкенда.

Запуск:  docker compose exec worker python dev_run.py track.mp3 [htdemucs|htdemucs_6s]
Положи track.mp3 в папку worker/ (она смонтирована в контейнер как /app).
Нужны таблицы в БД: миграции бэкенда или схема, выгруженная из dbdiagram (Export -> PostgreSQL).
"""
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

import repo
import s3
from tasks.process_audio import process_audio


def main() -> None:
    path = Path(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else "htdemucs"
    project_id = str(uuid.uuid4())
    key = f"sources/{project_id}.mp3"

    s3.upload(path, key)
    with Session(repo.engine) as session, session.begin():
        user_id = session.execute(text("SELECT id FROM users WHERE email = 'dev@local'")).scalar()
        if user_id is None:
            user_id = str(uuid.uuid4())
            session.execute(
                text("INSERT INTO users (id, email, password_hash) VALUES (:id, 'dev@local', 'x')"),
                {"id": user_id},
            )

        session.execute(
                    text(
                        "INSERT INTO project_states (project_id) VALUES (:id)"
                    ),
                    {"id": project_id},
                )


        session.execute(
            text(
                "INSERT INTO projects (id, user_id, name, status, model, source_file_key) "
                "VALUES (:id, :uid, :name, 'processing', :model, :key)"
            ),
            {"id": project_id, "uid": str(user_id), "name": path.stem, "model": model, "key": key},
        )
        


    process_audio.delay(project_id)  # через очередь: подхватит запущенный воркер
    print(f"проект {project_id} создан, задача поставлена. Логи: docker compose logs -f worker")

    while True:
        time.sleep(3)
        project = repo.get_project(uuid.UUID(project_id))
        print("статус:", project["status"])
        if project["status"] != "processing":
            break
    print("duration_sec:", project["duration_sec"], "| error_message:", project["error_message"])
    with Session(repo.engine) as session:
        rows = session.execute(
            text("SELECT stem_type, file_key FROM tracks WHERE project_id = :id ORDER BY stem_type"),
            {"id": project_id},
        ).all()
    for stem, file_key in rows:
        print(" ", stem, "->", file_key)


if __name__ == "__main__":
    main()
