import logging

from cdc.schemas.cdc_event import CDCEvent
from cdc.services.audit import AuditService
from utils.database import get_session_factory

logger = logging.getLogger(__name__)


class AuditHandler:
    """
    Handles audit persistence for CDC events.
    """

    SKIP_OPERATIONS = {"r"}

    SKIP_TABLES = {
        "audit_logs",
    }

    def __init__(self, session_factory=None):
        self.service = self.service = AuditService(session_factory or get_session_factory())

        self.stats = {
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "successful": 0,
        }

    async def handle(
        self,
        event: CDCEvent,
    ) -> bool:
        self.stats["processed"] += 1

        if self._should_skip(event):
            self.stats["skipped"] += 1

            logger.debug(
                f"Skipping audit for " f"{event.operation_name} on {event.table}"
            )

            return True

        logger.debug(
            f"Processing audit for "
            f"{event.operation_name} "
            f"on {event.table}[id={event.record_id}]"
        )

        try:
            audit = await self.service.record(event)

            if audit is None:
                self.stats["failed"] += 1
                return False

            self.stats["successful"] += 1

            logger.debug(
                f"Successfully recorded audit for "
                f"{event.table}[id={event.record_id}]"
            )

            return True

        except Exception:
            self.stats["failed"] += 1

            logger.exception(
                f"Failed to write audit log for " f"{event.table}[id={event.record_id}]"
            )

            return False

    def _should_skip(
        self,
        event: CDCEvent,
    ) -> bool:
        if event.operation in self.SKIP_OPERATIONS:
            return True

        if event.table.lower() in self.SKIP_TABLES:
            return True

        return False
