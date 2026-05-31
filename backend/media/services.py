from datetime import datetime, timezone, timedelta
import hashlib
import uuid
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from sqlalchemy import func, select
from fastapi import HTTPException, UploadFile, status, BackgroundTasks
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
from utils.validators import FileValidator
from core.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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
        self._url_cache: Dict[str, tuple[str, datetime]] = {}

    async def _generate_storage_key(
        self,
        media_asset_id: int,
        filename: str,
        media_type: str,
        is_temp: bool = False,
    ) -> str:
        """Generate storage key for file"""
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
        unique_id = str(uuid.uuid4())[:8]

        prefix = "temp" if is_temp else f"{media_type}s"

        return f"{prefix}/{timestamp}/{media_asset_id}_{unique_id}_{filename}"

    async def _compute_file_hash(
        self,
        file: UploadFile,
        chunk_size: int = 1024 * 1024,
    ) -> tuple[str, int]:
        """Computes MD5 hash and size without loading entire file into memory"""
        md5 = hashlib.md5()
        total_size = 0

        while chunk := await file.read(chunk_size):
            md5.update(chunk)
            total_size += len(chunk)

        await file.seek(0)

        return md5.hexdigest(), total_size

    async def _get_cached_presigned_url(
        self, storage_key: str, expires: int = 3600
    ) -> Optional[str]:
        """Get cached presigned URL if still valid"""
        cache_key = f"{storage_key}_{expires}"
        if cache_key in self._url_cache:
            url, expiry = self._url_cache[cache_key]
            if datetime.now() < expiry:
                return url
            else:
                del self._url_cache[cache_key]
        return None

    async def _cache_presigned_url(
        self, storage_key: str, url: str, expires: int = 3600
    ) -> None:
        """Cache presigned URL"""
        cache_key = f"{storage_key}_{expires}"
        expiry = datetime.now() + timedelta(seconds=expires - 60)  
        self._url_cache[cache_key] = (url, expiry)

    async def _get_presigned_url_with_cache(
        self, storage_key: str, expires: int = 3600
    ) -> str:
        """Get presigned URL with caching"""

        cached_url = await self._get_cached_presigned_url(storage_key, expires)
        if cached_url:
            return cached_url

        url = await self.storage_service.generate_presigned_url(
            bucket=None,
            key=storage_key,
            expires=expires,
        )

        await self._cache_presigned_url(storage_key, url, expires)

        return url

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
                file_url = await self._get_presigned_url_with_cache(
                    asset.original_file.storage_key,
                    expires=settings.PRESIGNED_URL_EXPIRY,
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
            logger.warning(f"Media asset not found: {identifier}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        original_file = await self.original_file_repository.get_by_media_asset_id(
            media_asset.id
        )

        file_url = None
        if original_file:
            file_url = await self._get_presigned_url_with_cache(
                original_file.storage_key, expires=settings.PRESIGNED_URL_EXPIRY
            )

        return MediaAssetResponse.model_validate(
            media_asset,
            from_attributes=True,
        ).model_copy(update={"file_url": file_url})

    async def create_media_asset_with_file(
        self,
        data: MediaAssetCreate,
        file: UploadFile,
        background_tasks: BackgroundTasks,
    ):
        """Create media asset with file upload - improved with validation and temp storage"""

        # Validate input
        FileValidator.validate_title(data.title)
        await FileValidator.validate_media_file(file, data.media_type.value)

        # Check for existing asset with same title
        stmt = self.media_asset_repository.build_query(filters={"title": data.title})
        result = await self.media_asset_repository.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.warning(f"Duplicate media asset title: {data.title}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Media asset already exists.",
            )

        # Compute file hash and check for duplicates
        file_hash, file_size = await self._compute_file_hash(file)

        existing_file = await self.original_file_repository.get_by_checksum(file_hash)
        if existing_file:
            logger.info(f"Duplicate file detected with hash: {file_hash}")
            existing_asset = await self.media_asset_repository.get_by_id(
                existing_file.media_asset_id
            )
            if existing_asset:
                # Return existing asset instead of creating duplicate
                return MediaAssetResponse.model_validate(existing_asset)

        # Create media asset with UPLOADING status
        media_asset = MediaAsset(
            title=data.title,
            description=data.description,
            media_type=data.media_type,
            duration_seconds=data.duration_seconds,
            status=MediaAssetStatus.UPLOADING,
        )

        temp_storage_key = None
        final_storage_key = None

        try:
            # Create asset record
            created_asset = await self.media_asset_repository.create(media_asset)
            await self.media_asset_repository.session.flush()

            # Upload to temporary location
            temp_storage_key = await self._generate_storage_key(
                media_asset_id=created_asset.id,
                filename=file.filename,
                media_type=data.media_type.value,
                is_temp=True,
            )

            logger.info(f"Uploading file to temp location: {temp_storage_key}")
            await self.storage_service.upload_file(
                bucket=None,
                key=temp_storage_key,
                file_obj=file.file,
                content_type=file.content_type or "application/octet-stream",
            )

            # Move to final location
            final_storage_key = await self._generate_storage_key(
                media_asset_id=created_asset.id,
                filename=file.filename,
                media_type=data.media_type.value,
                is_temp=False,
            )

            logger.info(f"Moving file from temp to final: {final_storage_key}")
            await self.storage_service.move_file(
                source_bucket=None,
                source_key=temp_storage_key,
                destination_bucket=None,
                destination_key=final_storage_key,
            )

            # Create original file record
            original_file = OriginalMediaFile(
                media_asset_id=created_asset.id,
                storage_key=final_storage_key,
                filename=file.filename,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=file_size,
                checksum=file_hash,
            )

            await self.original_file_repository.create(original_file)

            # Create processing job
            processing_job = ProcessingJob(
                media_asset_id=created_asset.id,
                job_type=ProcessingJobType.TRANSCODE,
                status=ProcessingJobStatus.QUEUED,
                progress=0,
            )

            await self.processing_job_repository.create(processing_job)

            # Update asset status
            created_asset.status = MediaAssetStatus.UPLOADED

            # Commit all changes
            await self.media_asset_repository.session.commit()

            # Refresh instances
            await self.media_asset_repository.session.refresh(created_asset)
            await self.original_file_repository.session.refresh(original_file)
            await self.processing_job_repository.session.refresh(processing_job)

            # Generate presigned URL
            file_url = await self._get_presigned_url_with_cache(
                final_storage_key, expires=settings.PRESIGNED_URL_EXPIRY
            )

            # Add background task for actual processing
            if settings.USE_BACKGROUND_TASKS:
                background_tasks.add_task(
                    self._process_media_asset_background,
                    created_asset.id,
                    final_storage_key,
                )

            logger.info(f"Successfully created media asset {created_asset.id}")

            response = MediaAssetResponse.model_validate(created_asset, from_attributes=True)
            response.file_url = file_url

            return response

        except Exception as exc:
            logger.error(f"Failed to upload media asset: {str(exc)}", exc_info=True)
            await self.media_asset_repository.session.rollback()

            # Clean up temp file if it exists
            if temp_storage_key:
                try:
                    await self.storage_service.delete_file(bucket=None, key=temp_storage_key)
                    logger.info(f"Cleaned up temp file: {temp_storage_key}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup temp file {temp_storage_key}: {cleanup_error}")

            # Clean up final file if it exists (in case move succeeded but DB failed)
            if final_storage_key:
                try:
                    await self.storage_service.delete_file(bucket=None, key=final_storage_key)
                    logger.info(f"Cleaned up final file: {final_storage_key}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup final file {final_storage_key}: {cleanup_error}")

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload media asset: {str(exc)}",
            )

    async def _process_media_asset_background(self, asset_id: int, storage_key: str):
        """Background task for media processing"""
        try:
            logger.info(f"Starting background processing for asset {asset_id}")

            # Update status to PROCESSING
            media_asset = await self.media_asset_repository.get_by_id(asset_id)
            if media_asset:
                media_asset.status = MediaAssetStatus.PROCESSING
                await self.media_asset_repository.update(media_asset)
                await self.media_asset_repository.session.commit()

            # Here you would implement actual processing:
            # - Generate thumbnails
            # - Create different quality representations
            # - Generate waveform for audio
            # - Update duration if not provided

            # For now, just mark as READY
            if media_asset:
                media_asset.status = MediaAssetStatus.READY
                await self.media_asset_repository.update(media_asset)
                await self.media_asset_repository.session.commit()

            logger.info(f"Successfully processed asset {asset_id}")

        except Exception as e:
            logger.error(
                f"Background processing failed for asset {asset_id}: {str(e)}",
                exc_info=True,
            )
            # Update status to FAILED
            media_asset = await self.media_asset_repository.get_by_id(asset_id)
            if media_asset:
                media_asset.status = MediaAssetStatus.FAILED
                await self.media_asset_repository.update(media_asset)
                await self.media_asset_repository.session.commit()

    async def create_media_asset_only(self, data: MediaAssetCreate):
        """Create media asset metadata only"""
        FileValidator.validate_title(data.title)

        stmt = self.media_asset_repository.build_query(filters={"title": data.title})
        result = await self.media_asset_repository.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            logger.warning(f"Duplicate media asset title: {data.title}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Media asset already exists.",
            )

        media_asset = MediaAsset(**data.model_dump())
        created = await self.media_asset_repository.create(media_asset)
        await self.media_asset_repository.session.commit()
        await self.media_asset_repository.session.refresh(created)

        logger.info(f"Created media asset metadata: {created.id}")

        return MediaAssetResponse.model_validate(created, from_attributes=True)

    async def update_media_asset(
        self,
        identifier: str,
        data: MediaAssetUpdate,
    ):
        """Update media asset metadata"""
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)

        if not media_asset:
            logger.warning(f"Media asset not found for update: {identifier}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        if data.title and data.title != media_asset.title:
            FileValidator.validate_title(data.title)

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

        logger.info(f"Updated media asset: {updated.id}")

        return MediaAssetResponse.model_validate(updated, from_attributes=True)


    async def update_media_asset_file(
        self,
        identifier: str,
        file: UploadFile,
        background_tasks: BackgroundTasks,
    ):
        """Replace the file for an existing media asset"""
        # Get existing asset
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)
        if not media_asset:
            logger.warning(f"Media asset not found for file update: {identifier}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found."
            )

        # Validate new file
        await FileValidator.validate_media_file(file, media_asset.media_type.value)

        # Get existing original file
        old_file = await self.original_file_repository.get_by_media_asset_id(media_asset.id)

        # Compute new file hash
        file_hash, file_size = await self._compute_file_hash(file)

        # Check for duplicate file
        existing_file = await self.original_file_repository.get_by_checksum(file_hash)
        if existing_file and (not old_file or existing_file.id != old_file.id):
            logger.warning(f"Duplicate file detected for asset {media_asset.id}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="File with same checksum already exists",
            )

        # Update status to UPLOADING
        media_asset.status = MediaAssetStatus.UPLOADING
        await self.media_asset_repository.update(media_asset)

        temp_storage_key = None
        final_storage_key = None
        old_storage_key = old_file.storage_key if old_file else None

        try:
            # Upload to temporary location
            temp_storage_key = await self._generate_storage_key(
                media_asset_id=media_asset.id,
                filename=file.filename,
                media_type=media_asset.media_type.value,
                is_temp=True,
            )

            logger.info(f"Uploading new file to temp location: {temp_storage_key}")
            await self.storage_service.upload_file(
                bucket=None,
                key=temp_storage_key,
                file_obj=file.file,
                content_type=file.content_type or "application/octet-stream",
            )

            # Generate final storage key
            final_storage_key = await self._generate_storage_key(
                media_asset_id=media_asset.id,
                filename=file.filename,
                media_type=media_asset.media_type.value,
                is_temp=False,
            )

            # Move from temp to final location
            logger.info(f"Moving file from temp to final: {final_storage_key}")
            await self.storage_service.move_file(
                source_bucket=None,
                source_key=temp_storage_key,
                destination_bucket=None,
                destination_key=final_storage_key,
            )

            # Clear temp key since file has been moved
            temp_storage_key = None

            # Update or create original file record
            if old_file:
                # Update existing record
                old_file.storage_key = final_storage_key
                old_file.filename = file.filename
                old_file.content_type = file.content_type or "application/octet-stream"
                old_file.size_bytes = file_size
                old_file.checksum = file_hash
                await self.original_file_repository.update(old_file)
                original_file_record = old_file
            else:
                # Create new record
                original_file_record = OriginalMediaFile(
                    media_asset_id=media_asset.id,
                    storage_key=final_storage_key,
                    filename=file.filename,
                    content_type=file.content_type or "application/octet-stream",
                    size_bytes=file_size,
                    checksum=file_hash,
                )
                await self.original_file_repository.create(original_file_record)

            # Create new processing job
            processing_job = ProcessingJob(
                media_asset_id=media_asset.id,
                job_type=ProcessingJobType.TRANSCODE,
                status=ProcessingJobStatus.QUEUED,
                progress=0,
            )
            await self.processing_job_repository.create(processing_job)

            # Update asset status
            media_asset.status = MediaAssetStatus.UPLOADED
            await self.media_asset_repository.update(media_asset)

            # Commit all changes
            await self.media_asset_repository.session.commit()

            # Refresh instances
            await self.media_asset_repository.session.refresh(media_asset)
            await self.original_file_repository.session.refresh(original_file_record)
            await self.processing_job_repository.session.refresh(processing_job)

            # Clean up old file in background
            if old_storage_key:
                logger.info(f"Queueing old file deletion: {old_storage_key}")
                background_tasks.add_task(
                    self._delete_file_with_logging,
                    old_storage_key,
                )

                # Clear old file from cache
                cache_key = f"{old_storage_key}_{settings.PRESIGNED_URL_EXPIRY}"
                self._url_cache.pop(cache_key, None)

            # Process new file in background
            if settings.USE_BACKGROUND_TASKS:
                background_tasks.add_task(
                    self._process_media_asset_background,
                    media_asset.id,
                    final_storage_key,
                )

            logger.info(f"Successfully updated file for asset {media_asset.id}")

            # Generate presigned URL for the new file
            file_url = await self._get_presigned_url_with_cache(
                final_storage_key, expires=settings.PRESIGNED_URL_EXPIRY
            )

            response = MediaAssetResponse.model_validate(media_asset, from_attributes=True)
            response.file_url = file_url

            return response

        except Exception as exc:
            logger.error(
                f"Failed to update file for asset {media_asset.id}: {str(exc)}",
                exc_info=True,
            )
            await self.media_asset_repository.session.rollback()

            # Clean up temp file if it exists
            if temp_storage_key:
                try:
                    await self.storage_service.delete_file(
                        bucket=None, key=temp_storage_key
                    )
                    logger.info(f"Cleaned up temp file: {temp_storage_key}")
                except Exception as cleanup_error:
                    logger.error(
                        f"Failed to cleanup temp file {temp_storage_key}: {cleanup_error}"
                    )

            # Clean up final file if it exists (in case move succeeded but DB failed)
            if final_storage_key:
                try:
                    await self.storage_service.delete_file(
                        bucket=None, key=final_storage_key
                    )
                    logger.info(f"Cleaned up final file: {final_storage_key}")
                except Exception as cleanup_error:
                    logger.error(
                        f"Failed to cleanup final file {final_storage_key}: {cleanup_error}"
                    )

            # Restore old status
            media_asset.status = MediaAssetStatus.FAILED
            await self.media_asset_repository.update(media_asset)
            await self.media_asset_repository.session.commit()

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update media asset file: {str(exc)}",
            )


async def _delete_file_with_logging(self, storage_key: str):
    """Delete file with logging"""
    try:
        await self.storage_service.delete_file(bucket=None, key=storage_key)
        logger.info(f"Successfully deleted old file: {storage_key}")
    except Exception as e:
        logger.error(f"Failed to delete old file {storage_key}: {str(e)}")
    async def delete_media_asset(
        self,
        identifier: str,
        hard: bool = False,
    ):
        """Delete media asset"""
        media_asset = await self.media_asset_repository.get_by_identifier(identifier)

        if not media_asset:
            logger.warning(f"Media asset not found for deletion: {identifier}")
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
                cache_key = (
                    f"{original_file.storage_key}_{settings.PRESIGNED_URL_EXPIRY}"
                )
                self._url_cache.pop(cache_key, None)

            await self.media_asset_repository.hard_delete(media_asset)
            logger.info(f"Hard deleted media asset {media_asset.id}")

        else:
            await self.media_asset_repository.soft_delete(media_asset)
            media_asset.status = MediaAssetStatus.DELETED
            await self.media_asset_repository.update(media_asset)
            logger.info(f"Soft deleted media asset {media_asset.id}")

        await self.media_asset_repository.session.commit()
