from services.audit import AuditService


class AuditHandler:

    def __init__(self):
        self.service = AuditService()

    async def handle(self, event):

        await self.service.record(event)
