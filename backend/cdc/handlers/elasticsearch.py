import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from cdc.schemas.cdc_event import CDCEvent

from media.models import MediaAsset

from search.document_builders.media_assets import MediaAssetDocumentBuilder
from search.index_registry import MEDIA_ASSETS_INDEX

from utils.elasticsearch import get_elasticsearch_client
from utils.database import get_session_factory

logger = logging.getLogger(__name__)


class ElasticsearchHandler:

    SEARCHABLE_TABLES = {"media_assets"}

    def __init__(self):
        self.es = get_elasticsearch_client()
        self.session_factory = get_session_factory()

    async def handle(self, event: CDCEvent):

        if event.table not in self.SEARCHABLE_TABLES:
            return

        try:
            if event.operation == "d":
                await self._handle_delete(event)
                return

            await self._handle_upsert(event)

        except Exception:
            logger.exception(f"Failed ES sync for {event.table}[id={event.record_id}]")

    async def _handle_upsert(self, event: CDCEvent):

        async with self.session_factory() as session:

            stmt = (
                select(MediaAsset)
                .where(MediaAsset.id == int(event.record_id))
                .options(
                    selectinload(MediaAsset.thumbnails),
                    selectinload(MediaAsset.representations),
                )
            )

            result = await session.execute(stmt)
            media_asset = result.scalar_one_or_none()

            if not media_asset:
                logger.warning(f"MediaAsset not found for indexing: {event.record_id}")
                return

            document = MediaAssetDocumentBuilder.build(media_asset)

            await self.es.index(
                index=MEDIA_ASSETS_INDEX,
                id=str(media_asset.id),
                document=document,
                refresh=False,
            )

    async def _handle_delete(self, event: CDCEvent):

        await self.es.delete(
            index=MEDIA_ASSETS_INDEX,
            id=str(event.record_id),
            refresh=False,
            ignore=[404],
        )
