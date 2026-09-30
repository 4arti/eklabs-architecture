from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.type_api import TypeEngine

# Stable, predictable names for every constraint Alembic generates, so
# autogenerate diffs don't churn on Postgres's default auto-named constraints.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every migration declares timestamp columns as TIMESTAMP(timezone=True)
    # (see migrations/versions/0002's _TS), but SQLAlchemy's own default for
    # a bare `Mapped[datetime]` is a naive DateTime. Overriding that default
    # here, once, for every model, instead of passing DateTime(timezone=True)
    # on each mapped_column(). Without this, a column populated purely by
    # server_default=now() never notices the mismatch (no Python value is
    # ever bound), but the moment app code supplies its own tz-aware
    # datetime (e.g. record_event()'s at=datetime.now(UTC)), asyncpg's
    # codec fails encoding it against the wrongly-inferred "without time
    # zone" bind cast.
    type_annotation_map: ClassVar[dict[type, TypeEngine[Any]]] = {datetime: DateTime(timezone=True)}
