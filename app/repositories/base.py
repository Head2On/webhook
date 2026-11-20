"""Base repository interface establishing database access boundary."""

from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository[ModelType: Base]:
    """Generic base repository for database interaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
