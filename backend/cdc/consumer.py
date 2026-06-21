import asyncio
import logging

from cdc.events.parser import parse_message
from cdc.handlers.audit import AuditHandler
from cdc.handlers.elasticsearch import ElasticsearchHandler
# from cdc.handlers.redis import RedisHandler

logger = logging.getLogger(__name__)


class CDCConsumer:
    """
    CDC event consumer that dispatches events to multiple handlers.
    """

    def __init__(self):
        # split critical vs non-critical handlers
        self.critical_handlers = [
            AuditHandler(),
        ]

        self.best_effort_handlers = [
            ElasticsearchHandler(),
            # RedisHandler(),
        ]

    async def process(self, message: dict):
        """
        Process a single CDC message.
        """

        event = parse_message(message)

        best_effort_results = await asyncio.gather(
            *[h.handle(event) for h in self.best_effort_handlers],
            return_exceptions=True,
        )

        for handler, result in zip(self.best_effort_handlers, best_effort_results):
            if isinstance(result, Exception):
                logger.exception(
                    f"{handler.__class__.__name__} failed",
                    exc_info=result,
                )

        for handler in self.critical_handlers:
            try:
                await handler.handle(event)
            except Exception:
                logger.exception(
                    f"Critical handler failed: {handler.__class__.__name__}"
                )
