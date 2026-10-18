from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class MoneyType(TypeDecorator):
    """Stores Decimal as exact text so SQLite never converts money to binary floats."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else format(Decimal(value), "f")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            return Decimal(value)
        except InvalidOperation:
            return None


class UTCDateTime(TypeDecorator):
    """SQLite drops tzinfo; always hand back timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
    return create_engine(url, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
