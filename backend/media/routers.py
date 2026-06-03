from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
    UploadFile,
    File,
    Form,
    BackgroundTasks,  
    HTTPException
)
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from utils.database import get_session
from utils.s3storage import (
    S3StorageService,
    AsyncStorageService,
)
from utils.logging import setup_logging

from .models import MediaType
from .repository import (
    MediaAssetRepository,
    OriginalMediaFileRepository,
    ProcessingJobRepository,
)
from .schemas import (
    MediaAssetCreate,
    MediaAssetUpdate,
    MediaAssetListFilters,
    MediaAssetResponse,
    MediaAssetListItem
)
from .services import MediaAssetService
from typing import Optional, List

setup_logging()


def get_storage_service() -> AsyncStorageService:
    return AsyncStorageService(S3StorageService())


def get_media_asset_service(
    session: AsyncSession = Depends(get_session),
    storage_service: AsyncStorageService = Depends(get_storage_service),
) -> MediaAssetService:
    return MediaAssetService(
        media_asset_repository=MediaAssetRepository(session),
        original_file_repository=OriginalMediaFileRepository(session),
        processing_job_repository=ProcessingJobRepository(session),
        storage_service=storage_service,
    )


media_asset_router = APIRouter(
    prefix="/media-assets",
    tags=["Media Assets"],
    responses={
        404: {"description": "Not found"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
    },
)


@media_asset_router.get(
    "/",
    status_code=status.HTTP_200_OK,
    response_model=Page[MediaAssetResponse],
)
async def list_media_assets(
    filters: MediaAssetListFilters = Depends(),
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    List media assets.

    Examples:
    - `?page=1&size=20`
    - `?media_type=video`
    - `?search=fastapi`
    """
    return await service.list_media_assets(filters)


@media_asset_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=MediaAssetResponse,
)
async def create_media_asset(
    data: MediaAssetCreate,
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    Create media asset metadata only.

    Content-Type: application/json
    """
    return await service.create_media_asset_only(data)


@media_asset_router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=MediaAssetResponse,
)
async def upload_media_asset(
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    description: str | None = Form(None),
    media_type: MediaType = Form(...),
    duration_seconds: int | None = Form(None),
    file: UploadFile = File(...),
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    Upload media file and create asset.

    Content-Type: multipart/form-data

    Supported formats:
    - Video: MP4, MPEG, QuickTime (max 1GB)
    - Audio: MP3, MP4, WAV (max 100MB)
    """
    payload = MediaAssetCreate(
        title=title,
        description=description,
        media_type=media_type,
        duration_seconds=duration_seconds,
    )

    return await service.create_media_asset_with_file(
        data=payload,
        file=file,
        background_tasks=background_tasks,
    )


@media_asset_router.put(
    "/{identifier}/file",
    status_code=status.HTTP_200_OK,
    response_model=MediaAssetResponse,
)
async def replace_media_asset_file(
    identifier: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    Replace the file for an existing media asset.

    The old file will be deleted from storage after successful upload.
    A new processing job will be created for the new file.
    """
    return await service.update_media_asset_file(
        identifier=identifier,
        file=file,
        background_tasks=background_tasks,
    )


@media_asset_router.get(
    "/{identifier}/",
    status_code=status.HTTP_200_OK,
    response_model=MediaAssetResponse,
)
async def get_media_asset(
    identifier: str,
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """Get media asset by ID, UUID, or slug"""
    return await service.get_media_asset(identifier)


@media_asset_router.patch(
    "/{identifier}/",
    status_code=status.HTTP_200_OK,
    response_model=MediaAssetResponse,
)
async def update_media_asset(
    identifier: str,
    data: MediaAssetUpdate,
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """Update media asset metadata only (title, description, etc.)"""
    return await service.update_media_asset(identifier, data)


@media_asset_router.delete(
    "/{identifier}/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media_asset(
    identifier: str,
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    Soft delete media asset by default.
    Use `?hard=true` for permanent deletion.
    """
    await service.delete_media_asset(identifier, hard=False)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@media_asset_router.get(
    "/library",
    status_code=status.HTTP_200_OK,
    response_model=Page[MediaAssetListItem],
)
async def get_media_library(
    filters: MediaAssetListFilters = Depends(),
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """Get media library with YouTube-like listing"""
    return await service.library.get_media_asset_list(filters)

