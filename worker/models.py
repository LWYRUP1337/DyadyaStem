from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, Uuid

metadata = MetaData()

projects = Table(
    "projects",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("status", String),
    Column("model", String),
    Column("duration_sec", Integer),
    Column("source_url", String),
    Column("source_file_key", String),
    Column("error_message", Text),
    Column("updated_at", DateTime),
)

tracks = Table(
    "tracks",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("project_id", Uuid),
    Column("stem_type", String),
    Column("file_key", String),
    Column("created_at", DateTime),  # заполняется значением по умолчанию на стороне БД
)
