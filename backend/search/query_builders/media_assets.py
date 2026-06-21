from search.rankings.media_assets import (
    MEDIA_ASSET_RANKING,
)


class MediaAssetQueryBuilder:

    @staticmethod
    def build_search_query(
        query: str,
        media_type: str | None = None,
        status: str | None = None,
    ) -> dict:

        filters = []

        if media_type:
            filters.append({
                "term": {
                    "media_type": media_type
                }
            })

        if status:
            filters.append({
                "term": {
                    "status": status
                }
            })

        return {
            "function_score": {

                "query": {
                    "bool": {

                        "must": [
                            {
                                "multi_match": {
                                    "query": query,

                                    "fields": [
                                        f"title^{MEDIA_ASSET_RANKING['title_weight']}",
                                        f"description^{MEDIA_ASSET_RANKING['description_weight']}",
                                    ],

                                    "type": "best_fields",

                                    "fuzziness": "AUTO",
                                }
                            }
                        ],

                        "filter": filters,
                    }
                },

                "functions": [

                    {
                        "filter": {
                            "term": {
                                "status": "ready"
                            }
                        },
                        "weight": MEDIA_ASSET_RANKING[
                            "ready_status_boost"
                        ]
                    },

                    {
                        "filter": {
                            "term": {
                                "title.keyword": query
                            }
                        },
                        "weight": MEDIA_ASSET_RANKING[
                            "exact_title_boost"
                        ]
                    },

                    {
                        "gauss": {
                            "created_at": {
                                "origin": "now",
                                "scale": "30d",
                                "offset": "7d",
                                "decay": 0.5
                            }
                        },

                        "weight": MEDIA_ASSET_RANKING[
                            "recent_upload_boost"
                        ]
                    }
                ],

                "score_mode": "sum",

                "boost_mode": "multiply"
            }
        }
