import uuid
from typing import TypeVar, Generic, Type, Optional, Any, Dict, List, Union
from datetime import datetime, timezone

from sqlalchemy import select, func, or_, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import BinaryExpression
from sqlalchemy.sql import Select
from sqlalchemy.exc import IntegrityError

from .models import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T], session: AsyncSession):
        self.model = model
        self.session = session

    def _get_searchable_fields(self) -> List[str]:
        """Get ILIKE search fields from model or auto-detect String columns"""
        fields = getattr(self.model, "__searchable_fields__", None)
        if fields:
            return fields
        return [
            c.name for c in self.model.__table__.columns if isinstance(c.type, String)
        ]

    def _get_ordering_fields(self) -> List[str]:
        """Get allowed ordering fields from model"""
        return getattr(self.model, "__ordering_fields__", []) or []

    def _get_filterable_fields(self) -> List[str]:
        """Get allowed filter fields from model"""
        return getattr(self.model, "__filterable_fields__", []) or []

    def _supports_soft_delete(self) -> bool:
        return hasattr(self.model, "deleted_at")

    def _supports_slug(self) -> bool:
        return hasattr(self.model, "url_slug")

    def _supports_full_text(self) -> bool:
        return hasattr(self.model, "search_vector")

    def _base_query(self, include_deleted: bool = False) -> Select:
        """Create base query with soft delete filter"""
        stmt = select(self.model)

        if not include_deleted and self._supports_soft_delete():
            stmt = stmt.where(self.model.deleted_at.is_(None))

        return stmt

    def apply_simple_search(self, stmt: Select, search: str) -> Select:
        """Apply simple ILIKE search using model's __searchable_fields__"""
        search_fields = self._get_searchable_fields()

        if search_fields:
            search_clause = or_(
                *[getattr(self.model, f).ilike(f"%{search}%") for f in search_fields]
            )
            stmt = stmt.where(search_clause)

        return stmt

    def apply_full_text_search(
        self, stmt: Select, search: str, with_rank: bool = False
    ) -> Select:
        """Apply PostgreSQL full-text search using model's search_vector"""
        if not self._supports_full_text() or not search.strip():
            return stmt

        language = getattr(self.model, "__fulltext_language__", "english")
        tsquery = func.plainto_tsquery(language, search)
        stmt = stmt.where(self.model.search_vector.op("@@")(tsquery))

        if with_rank:
            rank = func.ts_rank(self.model.search_vector, tsquery)
            stmt = stmt.add_columns(rank).order_by(rank.desc())

        return stmt

    def apply_filters(self, stmt: Select, filters: Dict[str, Any]) -> Select:
        """Apply dynamic filters with validation against __filterable_fields__"""
        allowed_fields = self._get_filterable_fields()

        for field, value in filters.items():
            field_name = field.rsplit("__", 1)[0]

            if allowed_fields and field_name not in allowed_fields:
                raise ValueError(
                    f"Field '{field_name}' is not filterable. Allowed: {allowed_fields}"
                )

            stmt = stmt.where(self._build_filter(field, value))

        return stmt

    def apply_ordering(
        self, stmt: Select, ordering: Optional[List[str]] = None
    ) -> Select:
        """Apply ordering with validation against __ordering_fields__"""
        if not ordering:
            return stmt

        allowed_fields = self._get_ordering_fields()
        order_cols = []

        for field in ordering:
            desc = False
            if field.startswith("-"):
                desc = True
                field = field[1:]

            if allowed_fields and field not in allowed_fields:
                raise ValueError(
                    f"Cannot order by '{field}'. Allowed: {allowed_fields}"
                )

            col = getattr(self.model, field, None)
            if col is None:
                raise ValueError(
                    f"Cannot order by unknown field '{field}' on {self.model.__name__}"
                )

            if desc:
                order_cols.append(col.desc())
            else:
                order_cols.append(col)

        if order_cols:
            stmt = stmt.order_by(*order_cols)

        return stmt

    def build_query(
        self,
        include_deleted: bool = False,
        search: Optional[str] = None,
        full_text_search: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        ordering: Optional[List[str]] = None,
    ) -> Select:
        """
        Build a complete query with all options applied.
        Ready to be passed to fastapi_pagination.ext.sqlalchemy.paginate()

        Does NOT apply limit/offset - let pagination library handle that.
        """
        stmt = self._base_query(include_deleted=include_deleted)

        if filters:
            stmt = self.apply_filters(stmt, filters)

        if search:
            stmt = self.apply_simple_search(stmt, search)

        if full_text_search:
            stmt = self.apply_full_text_search(stmt, full_text_search)

        if ordering:
            stmt = self.apply_ordering(stmt, ordering)

        return stmt

    async def create(self, obj: T) -> T:
        """
        Create a new record.

        Note: Does NOT commit - let the service layer control transactions.
        Uses flush() to populate auto-generated fields (id, created_at, etc.).

        Raises:
            IntegrityError: If database constraints are violated (e.g., unique constraint)
        """
        try:
            self.session.add(obj)
            await self.session.flush()
            return obj
        except IntegrityError:
            raise

    async def create_many(self, objs: list[T]) -> list[T]:
        """
        Create multiple records in a single transaction.

        Does NOT commit.
        """
        try:
            self.session.add_all(objs)
            await self.session.flush()
            return objs
        except IntegrityError:
            raise

    async def update(self, obj: T) -> T:
        """
        Update an existing record.

        Note: Does NOT commit - let the service layer control transactions.
        The object should already be attached to the session (fetched via this repo).

        Raises:
            IntegrityError: If database constraints are violated
        """
        try:
            await self.session.flush()
            return obj
        except IntegrityError:
            raise

    async def get_by_id(
        self,
        obj_id: int,
        include_deleted: bool = False,
    ) -> Optional[T]:
        """
        Fetch a single record by integer primary key.

        Args:
            obj_id: The integer ID of the record to fetch
            include_deleted: If True, include soft-deleted records

        Returns:
            The model instance if found, None otherwise
        """
        stmt = self._base_query(include_deleted=include_deleted)
        stmt = stmt.where(self.model.id == obj_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_base_uuid(
        self,
        base_uuid: uuid.UUID,
        include_deleted: bool = False,
    ) -> Optional[T]:
        """
        Fetch a single record by public base_uuid.

        Args:
            base_uuid: The UUID identifier (public API)
            include_deleted: If True, include soft-deleted records

        Returns:
            The model instance if found, None otherwise
        """
        stmt = self._base_query(include_deleted=include_deleted)
        stmt = stmt.where(self.model.base_uuid == base_uuid)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(
        self,
        url_slug: str,
        include_deleted: bool = False,
    ) -> Optional[T]:
        """
        Fetch a single record by url_slug.

        Args:
            url_slug: The URL-friendly slug string
            include_deleted: If True, include soft-deleted records

        Returns:
            The model instance if found, None otherwise
        """
        if not self._supports_slug():
            raise ValueError(f"{self.model.__name__} does not support slug lookups")

        stmt = self._base_query(include_deleted=include_deleted)
        stmt = stmt.where(self.model.url_slug == url_slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        include_deleted: bool = False,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        """
        Fetch all records (with optional limit/offset).

        Warning: Avoid using without limit on large tables.
        Prefer build_query() + paginate for production use.
        """
        stmt = self._base_query(include_deleted=include_deleted)

        if limit:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_identifier(
        self,
        identifier: str,
        include_deleted: bool = False,
    ) -> Optional[T]:

        stmt = self._base_query(include_deleted=include_deleted)

        if identifier.isdigit():
            stmt = stmt.where(self.model.id == int(identifier))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        try:
            uuid_obj = uuid.UUID(identifier)
            stmt = self._base_query(include_deleted=include_deleted)
            stmt = stmt.where(self.model.base_uuid == uuid_obj)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
        except ValueError:
            pass

        if self._supports_slug():
            stmt = self._base_query(include_deleted=include_deleted)
            stmt = stmt.where(self.model.url_slug == identifier)
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

        return None

    async def soft_delete(
        self,
        obj: T,
        deleted_by: Optional[Union[str, int, uuid.UUID]] = None,
    ) -> None:
        """Mark as deleted (does not commit)"""
        if not hasattr(obj, "deleted_at"):
            raise ValueError(f"{self.model.__name__} does not support soft-delete")

        obj.deleted_at = datetime.now(timezone.utc)
        if deleted_by is not None and hasattr(obj, "deleted_by"):
            obj.deleted_by = str(deleted_by)

    async def hard_delete(self, obj: T) -> None:
        """Permanently delete (does not commit)"""
        await self.session.delete(obj)

    def _build_filter(self, field: str, value: Any) -> BinaryExpression:
        if "__" in field:
            name, op = field.rsplit("__", 1)
        else:
            name, op = field, "eq"

        col = getattr(self.model, name, None)
        if col is None:
            raise ValueError(f"Field '{name}' does not exist on {self.model.__name__}")

        if op == "eq":
            return col == value
        if op == "gt":
            return col > value
        if op == "gte":
            return col >= value
        if op == "lt":
            return col < value
        if op == "lte":
            return col <= value
        if op == "in":
            if not isinstance(value, (list, tuple, set)):
                raise ValueError("'in' filter expects a list/tuple/set value")
            return col.in_(value)
        if op == "range":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError("'range' filter expects a two-item list/tuple")
            start, end = value
            return col.between(start, end)

        raise ValueError(f"Unknown operator: {op}")
