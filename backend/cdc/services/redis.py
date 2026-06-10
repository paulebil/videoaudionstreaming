class RedisService:

    async def upsert(self, event):
        key = f"{event.table}:{event.record_id}"
        ...
