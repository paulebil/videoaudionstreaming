import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    declared_attr,
    mapped_column,
)


class Base(DeclarativeBase):
    """Base declarative model."""

    __abstract__ = True

    @declared_attr.directive
    def __table_args__(cls):
        return {"schema": "public"}


class AuditMixin(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    base_uuid: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        default=uuid.uuid4,
        nullable=False,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            Index(
                f"ix_{cls.__tablename__}_created_updated", "created_at", "updated_at"
            ),
            {"schema": "public"},
        )


class SlugMixin(AuditMixin):
    """Adds URL slug generation via Database Trigger."""

    __abstract__ = True

    __slug_source_field__ = "name"
    url_slug: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True
    )

    @declared_attr.directive
    def __table_args__(cls):
        parent_args = list(super().__table_args__ or ())
        parent_args.append(
            UniqueConstraint("url_slug", name=f"uq_{cls.__tablename__}_slug")
        )
        return tuple(parent_args)

    @classmethod
    def get_slug_trigger_sql_parts(cls):
        """
        Returns a LIST of SQL strings to create the slug trigger.
        Splitting them avoids asyncpg 'multiple commands' error.
        """
        if cls.__abstract__:
            return None

        source_field = getattr(cls, "__slug_source_field__", "name")
        table_name = cls.__tablename__
        schema = "public"

        return [
            f"""
            CREATE OR REPLACE FUNCTION {schema}.{table_name}_slugify() RETURNS trigger AS $$
            DECLARE
                slug_text TEXT;
            BEGIN
                slug_text := NEW.{source_field};
                IF slug_text IS NULL OR slug_text = '' THEN
                    slug_text := 'item-' || NEW.id;
                ELSE
                    slug_text := LOWER(slug_text);
                    slug_text := REGEXP_REPLACE(slug_text, '[^a-z0-9]+', '-', 'g');
                    slug_text := BTRIM(slug_text, '-');
                    slug_text := LEFT(slug_text, 200);
                END IF;
                NEW.url_slug := slug_text;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """,
            f"DROP TRIGGER IF EXISTS {table_name}_slug_trigger ON {schema}.{table_name};",
            f"""
            CREATE TRIGGER {table_name}_slug_trigger
            BEFORE INSERT ON {schema}.{table_name}
            FOR EACH ROW EXECUTE FUNCTION {schema}.{table_name}_slugify();
            """,
        ]


class SoftDeleteMixin(AuditMixin):
    __abstract__ = True

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, user_id: Optional[str] = None) -> None:
        self.deleted_at = datetime.now(timezone.utc)
        if user_id:
            self.deleted_by = str(user_id)

    def restore(self) -> None:
        self.deleted_at = None
        self.deleted_by = None

    @declared_attr.directive
    def __table_args__(cls):
        parent_args = list(super().__table_args__ or ())
        parent_args.extend(
            [
                Index(
                    f"ix_{cls.__tablename__}_active",
                    "deleted_at",
                    postgresql_where=text("deleted_at IS NULL"),
                ),
                Index(
                    f"ix_{cls.__tablename__}_deleted",
                    "deleted_at",
                    postgresql_where=text("deleted_at IS NOT NULL"),
                ),
            ]
        )
        return tuple(parent_args)


class FullTextMixin(SoftDeleteMixin):
    """Adds PostgreSQL full-text search support via Database Trigger."""

    __abstract__ = True

    __search_fields__ = []
    search_vector: Mapped[Optional[str]] = mapped_column(TSVECTOR, nullable=True)

    @declared_attr.directive
    def __table_args__(cls):
        parent_args = list(super().__table_args__ or ())
        if cls.__search_fields__:
            parent_args.append(
                Index(
                    f"ix_{cls.__tablename__}_fts",
                    "search_vector",
                    postgresql_using="gin",
                )
            )
        return tuple(parent_args)

    @classmethod
    def get_fts_trigger_sql_parts(cls):
        """
        Returns a LIST of SQL strings to create the FTS trigger.
        """
        if cls.__abstract__ or not cls.__search_fields__:
            return None

        table_name = cls.__tablename__
        schema = "public"
        fields_expr = " || ".join(
            [f"COALESCE(NEW.{field}, '')" for field in cls.__search_fields__]
        )

        return [
            f"""
            CREATE OR REPLACE FUNCTION {schema}.{table_name}_fts_update() RETURNS trigger AS $$
            begin
                new.search_vector := to_tsvector('english', {fields_expr});
                return new;
            end
            $$ LANGUAGE plpgsql;
            """,
            f"DROP TRIGGER IF EXISTS {table_name}_fts_trigger ON {schema}.{table_name};",
            f"""
            CREATE TRIGGER {table_name}_fts_trigger
            BEFORE INSERT OR UPDATE ON {schema}.{table_name}
            FOR EACH ROW EXECUTE FUNCTION {schema}.{table_name}_fts_update();
            """,
        ]

    @classmethod
    def search(cls, session: Session, query_string: str, limit: int = 100):
        if not cls.__search_fields__:
            return []
        ts_query = func.plainto_tsquery("english", query_string)
        rank = func.ts_rank(cls.search_vector, ts_query)
        stmt = (
            select(cls)
            .where(cls.search_vector.op("@@")(ts_query))
            .order_by(rank.desc())
            .limit(limit)
        )
        return session.scalars(stmt).all()


class BaseUtilityModel(FullTextMixin, SlugMixin):
    __abstract__ = True
    __ordering_fields__ = []
    __filterable_fields__ = []

    def __repr__(self) -> str:
        slug_part = f", slug={self.url_slug}" if self.url_slug else ""
        deleted_part = (
            " [DELETED]" if hasattr(self, "is_deleted") and self.is_deleted else ""
        )
        return f"<{self.__class__.__name__}(id={self.id}, uuid={self.base_uuid}{slug_part})>{deleted_part}"


@contextmanager
def session_scope(session_factory):
    session = session_factory()
    try:
        yield session
        session.commit()
    except IntegrityError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
