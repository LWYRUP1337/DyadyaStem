import uuid

from sqlalchemy import create_engine, delete, func, insert, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

import config
from models import projects, tracks

engine = create_engine(config.DATABASE_URL_SYNC, poolclass=NullPool)


def get_project(project_id: uuid.UUID) -> dict | None:
    with Session(engine) as session:
        row = session.execute(select(projects).where(projects.c.id == project_id)).mappings().first()
        return dict(row) if row else None


def clear_tracks(project_id: uuid.UUID) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(tracks).where(tracks.c.project_id == project_id))



def mark_ready(project_id: uuid.UUID, duration_sec: int, stem_keys: dict[str, str]) -> None:

    with Session(engine) as session, session.begin():
        session.execute(delete(tracks).where(tracks.c.project_id == project_id))
        session.execute(
            insert(tracks),
            [
                {"id": uuid.uuid4(), "project_id": project_id, "stem_type": stem, "file_key": key}
                for stem, key in stem_keys.items()
            ],
        )
        session.execute(
            update(projects)
            .where(projects.c.id == project_id)
            .values(status="ready", duration_sec=duration_sec, error_message=None, updated_at=func.now())
        )


def mark_error(project_id: uuid.UUID, message: str) -> None:
    with Session(engine) as session, session.begin():
        session.execute(delete(tracks).where(tracks.c.project_id == project_id))
        session.execute(
            update(projects)
            .where(projects.c.id == project_id)
            .values(status="error", error_message=message[:1000], updated_at=func.now())
        )
