from typing import Optional

from elasticsearch import AsyncElasticsearch

from core.settings import get_settings

_client: Optional[AsyncElasticsearch] = None


def get_elasticsearch_client() -> AsyncElasticsearch:
    """
    Create (once) and return the shared AsyncElasticsearch client.
    """
    global _client

    if _client is None:
        settings = get_settings()

        _client = AsyncElasticsearch(
            hosts=[settings.ELASTICSEARCH_URL],
            request_timeout=30,
            retry_on_timeout=True,
            max_retries=3,
            headers={
                "Accept": "application/vnd.elasticsearch+json; compatible-with=8",
                "Content-Type": "application/vnd.elasticsearch+json; compatible-with=8",
            },
        )

    return _client


async def close_elasticsearch() -> None:
    """
    Gracefully close the Elasticsearch client.
    """
    global _client

    if _client is not None:
        await _client.close()
        _client = None
