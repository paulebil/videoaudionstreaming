from media.models import MediaAsset


class MediaAssetDocumentBuilder:

    @staticmethod
    def build(media: MediaAsset) -> dict:

        thumbnail_key = None

        if media.thumbnails:
            thumbnail_key = media.thumbnails[0].storage_key

        representations = []

        for representation in media.representations:
            representations.append(
                {
                    "quality": representation.quality,
                    "bitrate": representation.bitrate,
                    "width": representation.width,
                    "height": representation.height,
                    "resolution": representation.resolution,
                }
            )

        return {
            "id": str(media.id),

            "title": media.title,

            "description": media.description,

            "media_type": media.media_type.value,

            "status": media.status.value,

            "duration_seconds": media.duration_seconds,

            "created_at": media.created_at.isoformat()
            if media.created_at
            else None,

            "thumbnail_storage_key": thumbnail_key,

            "representations": representations,
        }
