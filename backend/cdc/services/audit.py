import logging
from typing import Optional

from cdc.schemas.audit_entry import AuditEntry
from cdc.schemas.cdc_event import CDCEvent
from system.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Service responsible for persisting audit logs."""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def record(
        self,
        event: CDCEvent,
    ) -> Optional[AuditLog]:
        """
        Persist a CDC event as an audit log.

        Args:
            event: CDC event to persist

        Returns:
            Created AuditLog instance or None
        """
        if event.is_snapshot:
            logger.debug(f"Skipping snapshot event for table '{event.table}'")
            return None

        entry = AuditEntry(
            operation=event.operation,
            operation_name=event.operation_name,
            table=event.table,
            record_id=event.record_id,
            before_state=event.before,
            after_state=event.after,
            changed_fields=event.get_changed_fields(),
            timestamp=event.timestamp,
        )

        try:
            async with self.session_factory() as session:
                try:
                    audit = AuditLog(
                        operation=entry.operation,
                        operation_name=entry.operation_name,
                        table_name=entry.table,
                        record_id=entry.record_id,
                        before_state=entry.before_state,
                        after_state=entry.after_state,
                        changed_fields=entry.changed_fields,
                        event_timestamp=entry.timestamp,
                    )

                    session.add(audit)

                    await session.commit()
                    await session.refresh(audit)

                    logger.debug(
                        f"Audit recorded: "
                        f"{entry.operation_name} "
                        f"on {entry.table}[id={entry.record_id}]"
                    )

                    return audit

                except Exception:
                    await session.rollback()
                    raise

        except Exception as e:
            logger.exception(
                f"Failed to record audit for "
                f"{event.table}[id={event.record_id}]: {e}"
            )
            return None
