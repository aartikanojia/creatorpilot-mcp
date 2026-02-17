"""
SQLAlchemy declarative base and common model utilities.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import MetaData, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Naming convention for constraints (helps with Alembic migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.

    Provides:
    - Common metadata with naming conventions
    - Default __repr__ implementation
    - Timestamp mixins available via TimestampMixin
    """

    metadata = metadata

    def __repr__(self) -> str:
        """Generate a readable representation of the model."""
        class_name = self.__class__.__name__
        attrs = []
        for col in self.__table__.columns:
            if col.name in ("id", "name", "email", "channel_id", "user_id"):
                value = getattr(self, col.name, None)
                attrs.append(f"{col.name}={value!r}")
        return f"<{class_name}({', '.join(attrs)})>"


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamp columns.

    Usage:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_table"
            ...
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
