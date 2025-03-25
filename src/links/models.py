from sqlalchemy import Table, Column, Integer, MetaData, String,Boolean,DateTime

from sqlalchemy.dialects.postgresql import UUID
metadata = MetaData()

links = Table(
    "links",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("long_link", String),
    Column("short_link", String),
    Column("auth", Boolean),
    Column("user_id", UUID(as_uuid=True)),  # изменили тип на UUID
    Column("start_date", DateTime(timezone=True)),
    Column("last_date", DateTime(timezone=True)),
    Column("num", Integer),
    Column("expires_at", DateTime(timezone=True))
)