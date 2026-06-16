from sqlalchemy import BigInteger
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Index
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


from utils.models import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    operation: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
    )

    operation_name: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    table_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    record_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    before_state: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    after_state: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    changed_fields: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    event_timestamp: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_audit_table_record",
            "table_name",
            "record_id",
        ),
        Index(
            "idx_audit_operation",
            "operation",
        ),
    )
