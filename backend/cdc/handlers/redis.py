# from services.redis import RedisService


# class RedisHandler:

#     CACHEABLE_TABLES = {"media_assets", "processing_jobs", "thumbnails"}

#     def __init__(self):
#         self.service = RedisService()

#     async def handle(self, event):

#         if event.table not in self.CACHEABLE_TABLES:
#             return

#         await self.service.upsert(event)
