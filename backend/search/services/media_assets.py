from elasticsearch import NotFoundError

from search.document_builders.media_assets import (
    MediaAssetDocumentBuilder,
)

from search.index_registry import (
    MEDIA_ASSETS_INDEX,
)

from search.query_builders.media_assets import (
    MediaAssetQueryBuilder,
)

from utils.elasticsearch import (
    get_elasticsearch_client,
)


class MediaAssetSearchService:

    def __init__(self):
        self.client = get_elasticsearch_client()

    async def index_media_asset(
        self,
        media_asset,
    ):

        document = MediaAssetDocumentBuilder.build(
            media_asset
        )

        await self.client.index(
            index=MEDIA_ASSETS_INDEX,
            id=str(media_asset.id),
            document=document,
            refresh=False,
        )

    async def delete_media_asset(
        self,
        media_asset_id: int,
    ):

        try:
            await self.client.delete(
                index=MEDIA_ASSETS_INDEX,
                id=str(media_asset_id),
                refresh=False,
            )

        except NotFoundError:
            pass

    async def search(
        self,
        query: str,
        page: int = 1,
        page_size: int = 20,
        media_type: str | None = None,
        status: str | None = None,
    ):

        es_query = (
            MediaAssetQueryBuilder.build_search_query(
                query=query,
                media_type=media_type,
                status=status,
            )
        )

        response = await self.client.search(
            index=MEDIA_ASSETS_INDEX,

            query=es_query,

            from_=(page - 1) * page_size,

            size=page_size,
        )

        return {
            "total": response["hits"]["total"]["value"],
            "hits": response["hits"]["hits"],
        }

    async def autocomplete(
        self,
        query: str,
        size: int = 10,
    ):

        es_query = (
            MediaAssetQueryBuilder.build_autocomplete_query(
                query=query
            )
        )

        response = await self.client.search(
            index=MEDIA_ASSETS_INDEX,
            query=es_query,
            size=size,
        )

        return response["hits"]["hits"]
