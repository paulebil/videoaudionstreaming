import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from .models import (
    MediaAssetStatus,
    MediaType,
)


class MediaAssetCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = Field(
        default=None,
        max_length=10000,
    )
    media_type: MediaType
    duration_seconds: int | None = Field(
        default=None,
        ge=0,
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "title": "Introduction to FastAPI",
                "description": "Beginner tutorial covering FastAPI fundamentals.",
                "media_type": "video",
                "duration_seconds": 840,
            }
        },
    }


class MediaAssetUpdate(BaseModel):
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    description: str | None = Field(
        default=None,
        max_length=10000,
    )
    media_type: MediaType | None = None
    duration_seconds: int | None = Field(
        default=None,
        ge=0,
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "title": "Updated FastAPI Tutorial",
                "duration_seconds": 900,
            }
        },
    }


class MediaAssetListFilters(BaseModel):
    search: str | None = None
    full_text_search: str | None = None

    media_type: MediaType | None = None
    status: MediaAssetStatus | None = None

    ordering: list[str] | None = None

    limit: int | None = Field(
        default=None,
        ge=1,
    )

    offset: int | None = Field(
        default=None,
        ge=0,
    )

    def to_repository_filters(self) -> dict[str, object]:
        filters: dict[str, object] = {}

        if self.media_type is not None:
            filters["media_type"] = self.media_type

        if self.status is not None:
            filters["status"] = self.status

        return filters

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "search": "fastapi",
                "media_type": "video",
                "status": "ready",
                "ordering": [
                    "-created_at",
                    "title",
                ],
                "limit": 20,
                "offset": 0,
            }
        },
    }


class MediaAssetResponse(BaseModel):
    id: int
    base_uuid: uuid.UUID

    url_slug: str | None = None

    title: str
    description: str | None = None

    media_type: MediaType
    status: MediaAssetStatus

    duration_seconds: int | None = None

    file_url: str | None = None  

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "base_uuid": "d79bdb8a-b9d2-4678-93fa-7c4d12cb58f1",
                "url_slug": "introduction-to-fastapi",
                "title": "Introduction to FastAPI",
                "description": "Beginner tutorial covering FastAPI fundamentals.",
                "media_type": "video",
                "status": "ready",
                "duration_seconds": 840,
                "file_url": "https://rustfs.example.com/presigned/get/object.mp4?X-Amz-Algorithm=...",
                "created_at": "2026-05-30T12:00:00Z",
                "updated_at": "2026-05-30T12:15:00Z",
            }
        },
    }



class MediaAssetListItem(BaseModel):
    """
    Enhanced response for media asset list (YouTube-like interface)
    Contains all information needed for video cards/grid display
    """

    id: int
    base_uuid: uuid.UUID
    title: str
    description: str | None = None

    media_type: MediaType
    status: MediaAssetStatus
    duration_seconds: int | None = None

    thumbnail_small: str | None = Field(
        None, description="Small thumbnail (120x68) for list/card views"
    )
    thumbnail_medium: str | None = Field(
        None, description="Medium thumbnail (320x180) for grid/preview"
    )
    thumbnail_large: str | None = Field(
        None, description="Large thumbnail (640x360) for hero/featured"
    )

    hls_master_playlist: str | None = Field(
        None, description="HLS master playlist URL for adaptive streaming"
    )
    dash_manifest: str | None = Field(
        None, description="DASH manifest URL (future support)"
    )

    available_qualities: list[str] = Field(
        default_factory=list,
        description="Available video qualities (e.g., ['1080p', '720p', '480p'])",
    )

    view_count: int = Field(0, description="Total view count")
    like_count: int = Field(0, description="Total like count")
    comment_count: int = Field(0, description="Total comment count")

    is_liked: bool | None = Field(
        None, description="Whether current user has liked this video"
    )
    watch_progress: int | None = Field(
        None, description="Watch progress in seconds (for continue watching)"
    )

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "base_uuid": "550e8400-e29b-41d4-a716-446655440000",
                "title": "Introduction to FastAPI",
                "description": "Learn FastAPI from scratch",
                "media_type": "video",
                "status": "ready",
                "duration_seconds": 840,
                "thumbnail_small": "https://storage.example.com/thumbnails/1_1s.jpg",
                "thumbnail_medium": "https://storage.example.com/thumbnails/1_30s.jpg",
                "thumbnail_large": "https://storage.example.com/thumbnails/1_60s.jpg",
                "hls_master_playlist": "https://storage.example.com/hls/master.m3u8",
                "dash_manifest": None,
                "available_qualities": ["1080p", "720p", "480p"],
                "view_count": 1523,
                "like_count": 342,
                "comment_count": 56,
                "is_liked": None,
                "watch_progress": None,
                "created_at": "2026-06-03T10:00:00Z",
                "updated_at": "2026-06-03T10:00:00Z",
            }
        },
    }


