from services.elasticsearch import ElasticsearchService


class ElasticsearchHandler:

    SEARCHABLE_TABLES = {"media_assets", "processing_jobs"}

    def __init__(self):
        self.service = ElasticsearchService()

    async def handle(self, event):

        if event.table not in self.SEARCHABLE_TABLES:
            return

        if event.operation == "d":
            await self.service.delete(event)
        else:
            await self.service.index(event)
