from fastapi import APIRouter, Depends, Response, status
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from utils.database import get_session

from .repository import MediaAssetRepository, OriginalMediaFileRepository
from .schemas import (
    MediaAssetCreate,
    MediaAssetUpdate,
    MediaAssetListFilters,
    MediaAssetResponse,
)
from .services import MediaAssetService


def get_media_asset_service(
    session: AsyncSession = Depends(get_session),
) -> MediaAssetService:
    media_asset_repository = MediaAssetRepository(session)
    original_file_repository = OriginalMediaFileRepository(session)

    return MediaAssetService(
        media_asset_repository=media_asset_repository,
        original_file_repository=original_file_repository,
    )


media_asset_router = APIRouter(
    prefix="/media-assets",
    tags=["Media Assets"],
    responses={404: {"description": "Not found"}},
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
    List media assets with pagination.
    Query params: ?page=1&size=50&media_type=video&search=fastapi
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
    return await service.create_media_asset(data)


@media_asset_router.post(
    "/bulk",
    status_code=status.HTTP_201_CREATED,
    response_model=list[MediaAssetResponse],
)
async def create_media_assets(
    data: list[MediaAssetCreate],
    service: MediaAssetService = Depends(get_media_asset_service),
):
    return await service.create_media_assets(data)


@media_asset_router.get(
    "/{identifier}/",
    status_code=status.HTTP_200_OK,
    response_model=MediaAssetResponse,
)
async def get_media_asset(
    identifier: str,
    service: MediaAssetService = Depends(get_media_asset_service),
):
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
    """
    await service.delete_media_asset(identifier, hard=False)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
