"""Task and job models.

Re-exports Job and QueueEntry models from cl_server_shared.
Defines compute-specific models like ServiceConfig.
"""

from __future__ import annotations

from typing import override

from cl_server_shared.models import Base, Job, QueueEntry
from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column


class ServiceConfig(Base):
    """SQLAlchemy model for service configuration."""

    __tablename__ = "service_config"  # pyright: ignore[reportUnannotatedClassAttribute]

    # Primary key
    key: Mapped[str] = mapped_column(String, primary_key=True)

    # Configuration value (stored as string, parsed as needed)
    value: Mapped[str] = mapped_column(String, nullable=False)

    # Metadata
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)

    @override
    def __repr__(self) -> str:
        return f"<ServiceConfig(key={self.key}, value={self.value})>"


__all__ = ["Job", "QueueEntry", "ServiceConfig"]
