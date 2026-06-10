from events.parser import parse_message
from handlers.elasticsearch import ElasticsearchHandler
from handlers.redis import RedisHandler
from handlers.audit import AuditHandler

class CDCConsumer:

    def __init__(self):
        self.handlers = [
            ElasticsearchHandler(),
            RedisHandler(),
            AuditHandler(),
        ]

    async def process(self, message):
        event = parse_message(message)

        for handler in self.handlers:
            await handler.handle(event)
