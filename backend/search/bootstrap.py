from pathlib import Path
import json

from search.index_registry import INDEXES
from utils.elasticsearch import get_elasticsearch_client


async def init_search_indexes():
    """
    Initializes all Elasticsearch indexes defined in the registry.
    Safe to run on startup (idempotent).
    """

    es = get_elasticsearch_client()

    base_path = Path(__file__).resolve().parent

    for index, mapping_path in INDEXES.items():

        full_path = base_path / mapping_path

        if not full_path.exists():
            raise FileNotFoundError(f"Mapping not found: {full_path}")

        exists = await es.index_exists(index)
        if exists:
            continue

        with open(full_path, "r") as f:
            body = json.load(f)

        await es.create_index(index=index, body=body)
