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


class OriginalMediaFileCreate(BaseModel):
    media_asset_id: int = Field(..., gt=0)

    storage_key: str = Field(
        ...,
        min_length=1,
        max_length=1000,
    )

    filename: str = Field(
        ...,
        min_length=1,
        max_length=500,
    )

    content_type: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    size_bytes: int = Field(
        ...,
        ge=0,
    )

    checksum: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "media_asset_id": 1,
                "storage_key": "media/videos/intro-fastapi.mp4",
                "filename": "intro-fastapi.mp4",
                "content_type": "video/mp4",
                "size_bytes": 104857600,
                "checksum": "5d41402abc4b2a76b9719d911017c592",
            }
        },
    }


class OriginalMediaFileResponse(BaseModel):
    id: int
    base_uuid: uuid.UUID

    media_asset_id: int

    storage_key: str
    filename: str
    content_type: str
    size_bytes: int
    checksum: str

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": 1,
                "base_uuid": "c4d72f30-dc6a-4b4e-9485-5ef43f0f58f9",
                "media_asset_id": 1,
                "storage_key": "media/videos/intro-fastapi.mp4",
                "filename": "intro-fastapi.mp4",
                "content_type": "video/mp4",
                "size_bytes": 104857600,
                "checksum": "5d41402abc4b2a76b9719d911017c592",
                "created_at": "2026-05-30T12:00:00Z",
                "updated_at": "2026-05-30T12:00:00Z",
            }
        },
    }
