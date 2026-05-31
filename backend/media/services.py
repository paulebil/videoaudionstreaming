from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy import func, select

from fastapi import HTTPException, UploadFile, status
from fastapi_pagination import Page

from .models import (
    MediaAsset,
    OriginalMediaFile,
    ProcessingJob,
    MediaAssetStatus,
    ProcessingJobType,
    ProcessingJobStatus,
)
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
from utils.s3storage import AsyncStorageService


class MediaAssetService:
    def __init__(
        self,
        media_asset_repository: MediaAssetRepository,
        original_file_repository: OriginalMediaFileRepository,
        processing_job_repository: ProcessingJobRepository,
        storage_service: AsyncStorageService,
    ):
        self.media_asset_repository = media_asset_repository
        self.original_file_repository = original_file_repository
        self.processing_job_repository = processing_job_repository
        self.storage_service = storage_service

    async def _generate_storage_key(
        self,
        media_asset_id: int,
        filename: str,
        media_type: str,
    ) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
        unique_id = str(uuid.uuid4())[:8]

        return (
            f"{media_type}s/" f"{timestamp}/" f"{media_asset_id}_{unique_id}_{filename}"
        )

    async def _compute_file_hash(
        self,
        file: UploadFile,
        chunk_size: int = 1024 * 1024,
    ) -> tuple[str, int]:
        """
        Computes MD5 hash and size without loading the
        entire file into memory.
        """

        md5 = hashlib.md5()
        total_size = 0

        while chunk := await file.read(chunk_size):
            md5.update(chunk)
            total_size += len(chunk)

        await file.seek(0)

        return md5.hexdigest(), total_size

    def get_filtered_statement(self, filters: MediaAssetListFilters):
        return self.media_asset_repository.build_query(
            search=filters.search,
            full_text_search=filters.full_text_search,
            filters=filters.to_repository_filters() or None,
            ordering=filters.ordering,
        )

    async def list_media_assets(self, filters: MediaAssetListFilters):

        stmt = self.get_filtered_statement(filters)

        page_num = getattr(filters, "page", 1)
        page_size = getattr(filters, "size", 50)
        offset = (page_num - 1) * page_size

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.media_asset_repository.session.scalar(count_stmt)

        paginated_stmt = stmt.offset(offset).limit(page_size)
        result = await self.media_asset_repository.session.execute(paginated_stmt)
        items = list(result.scalars().all())

        processed_items = []
        for asset in items:  
            file_url = None
            if hasattr(asset, "original_file") and asset.original_file:
                file_url = await self.storage_service.generate_presigned_url(
                    bucket=None,
                    key=asset.original_file.storage_key,
                    expires=3600,
                )

            response = MediaAssetResponse.model_validate(asset)
            response.file_url = file_url
            processed_items.append(response)

        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        return Page(
            items=processed_items,
            total=total,
            page=page_num,
            size=page_size,
            pages=total_pages,
        )
    

    async def get_media_asset(self, identifier: str):
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)

        if not media_asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        original_file = await self.original_file_repository.get_by_media_asset_id(
            media_asset.id
        )

        file_url = None

        if original_file:
            file_url = await self.storage_service.generate_presigned_url(
                bucket=None,
                key=original_file.storage_key,
                expires=3600,
            )

        return MediaAssetResponse.model_validate(
            media_asset,
            from_attributes=True,
        ).model_copy(
            update={
                "file_url": file_url,
            }
        )

    async def create_media_asset_with_file(
        self,
        data: MediaAssetCreate,
        file: UploadFile,
    ):
        stmt = self.media_asset_repository.build_query(filters={"title": data.title})

        result = await self.media_asset_repository.session.execute(stmt)

        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Media asset already exists.",
            )

        file_hash, file_size = await self._compute_file_hash(file)

        media_asset = MediaAsset(
            title=data.title,
            description=data.description,
            media_type=data.media_type,
            duration_seconds=data.duration_seconds,
            status=MediaAssetStatus.UPLOADING,
        )

        try:
            created_asset = await self.media_asset_repository.create(media_asset)

            await self.media_asset_repository.session.flush()

            storage_key = await self._generate_storage_key(
                media_asset_id=created_asset.id,
                filename=file.filename,
                media_type=data.media_type.value,
            )

            await self.storage_service.upload_file(
                bucket=None,
                key=storage_key,
                file_obj=file.file,
                content_type=file.content_type or "application/octet-stream",
            )

            original_file = OriginalMediaFile(
                media_asset_id=created_asset.id,
                storage_key=storage_key,
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=file_size,
                checksum=file_hash,
            )

            created_original_file = await self.original_file_repository.create(
                original_file
            )

            processing_job = ProcessingJob(
                media_asset_id=created_asset.id,
                job_type=ProcessingJobType.TRANSCODE,
                status=ProcessingJobStatus.QUEUED,
                progress=0,
            )

            created_job = await self.processing_job_repository.create(processing_job)

            created_asset.status = MediaAssetStatus.UPLOADED

            await self.media_asset_repository.session.commit()

            await self.media_asset_repository.session.refresh(created_asset)

            await self.original_file_repository.session.refresh(created_original_file)

            await self.processing_job_repository.session.refresh(created_job)

            file_url = await self.storage_service.generate_presigned_url(
                bucket=None,
                key=storage_key,
                expires=3600,
            )

            response = MediaAssetResponse.model_validate(
                created_asset,
                from_attributes=True,
            )

            response.file_url = file_url

            return response

        except Exception as exc:
            await self.media_asset_repository.session.rollback()
            print(f"Failed to upload media asset: {str(exc)}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload media asset: {str(exc)}",
            )

    async def create_media_asset_only(
        self,
        data: MediaAssetCreate,
    ):
        stmt = self.media_asset_repository.build_query(filters={"title": data.title})

        result = await self.media_asset_repository.session.execute(stmt)

        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Media asset already exists.",
            )

        media_asset = MediaAsset(**data.model_dump())

        created = await self.media_asset_repository.create(media_asset)

        await self.media_asset_repository.session.commit()

        await self.media_asset_repository.session.refresh(created)

        return MediaAssetResponse.model_validate(
            created,
            from_attributes=True,
        )

    async def update_media_asset(
        self,
        identifier: str,
        data: MediaAssetUpdate,
    ):
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)

        if not media_asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        if data.title and data.title != media_asset.title:
            stmt = self.media_asset_repository.build_query(
                filters={"title": data.title}
            )

            result = await self.media_asset_repository.session.execute(stmt)

            existing = result.scalar_one_or_none()

            if existing and existing.id != media_asset.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Media asset title already exists.",
                )

        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(media_asset, key, value)

        updated = await self.media_asset_repository.update(media_asset)

        await self.media_asset_repository.session.commit()

        await self.media_asset_repository.session.refresh(updated)

        return MediaAssetResponse.model_validate(
            updated,
            from_attributes=True,
        )

    async def delete_media_asset(
        self,
        identifier: str,
        hard: bool = False,
    ):
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)

        if not media_asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        original_file = await self.original_file_repository.get_by_media_asset_id(
            media_asset.id
        )

        if hard:
            if original_file:
                await self.storage_service.delete_file(
                    bucket=None,
                    key=original_file.storage_key,
                )

            await self.media_asset_repository.hard_delete(media_asset)

        else:
            await self.media_asset_repository.soft_delete(media_asset)

            media_asset.status = MediaAssetStatus.DELETED

        await self.media_asset_repository.session.commit()
