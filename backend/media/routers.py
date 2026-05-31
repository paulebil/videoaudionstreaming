from fastapi import (
    APIRouter,
    Depends,
    Response,
    status,
    UploadFile,
    File,
    Form,
)
from fastapi_pagination import Page
from sqlalchemy.ext.asyncio import AsyncSession

from utils.database import get_session
from utils.s3storage import (
    S3StorageService,
    AsyncStorageService,
)

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
)
from .services import MediaAssetService

storage_service = AsyncStorageService(S3StorageService())


def get_media_asset_service(
    session: AsyncSession = Depends(get_session),
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
        404: {
            "description": "Not found",
        }
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

    ?page=1
    ?size=20
    ?media_type=video
    ?search=fastapi
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

    Content-Type:
    application/json
    """

    return await service.create_media_asset_only(data)

@media_asset_router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=MediaAssetResponse,
)
async def upload_media_asset(
    title: str = Form(...),
    description: str | None = Form(None),
    media_type: MediaType = Form(...),
    duration_seconds: int | None = Form(None),
    file: UploadFile = File(...),
    service: MediaAssetService = Depends(get_media_asset_service),
):
    """
    Upload media file and create asset.

    Content-Type:
    multipart/form-data
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
    return await service.update_media_asset(
        identifier,
        data,
    )


@media_asset_router.delete(
    "/{identifier}/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media_asset(
    identifier: str,
    service: MediaAssetService = Depends(get_media_asset_service),
):

    await service.delete_media_asset(
        identifier,
        hard=False,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
