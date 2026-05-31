from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from utils.repository import BaseRepository

from .models import (
    MediaAsset,
    OriginalMediaFile,
    ProcessingJob,
    MediaRepresentation,
    StreamingManifest,
    Thumbnail,
    MediaAssetStatus,
    ProcessingJobStatus,
)


class MediaAssetRepository(BaseRepository[MediaAsset]):
    def __init__(self, session: AsyncSession):
        super().__init__(MediaAsset, session)


    def apply_joins(self, stmt):
        return stmt.options(selectinload(MediaAsset.original_file))

    async def get_by_title(
        self,
        title: str,
    ) -> MediaAsset | None:
        stmt = self._base_query().where(MediaAsset.title == title)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_status(
        self,
        status: MediaAssetStatus,
    ) -> list[MediaAsset]:
        stmt = (
            self._base_query()
            .where(MediaAsset.status == status)
            .order_by(MediaAsset.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_media_asset(
        self,
        identifier: str,
        hard: bool = False,
        deleted_by: str | None = None,
    ) -> bool:
        media_asset = await self.get_by_identifier(
            identifier,
            include_deleted=hard,
        )

        if media_asset is None:
            return False

        if hard:
            await self.hard_delete(media_asset)
        else:
            await self.soft_delete(
                media_asset,
                deleted_by=deleted_by,
            )

        return True


class OriginalMediaFileRepository(BaseRepository[OriginalMediaFile]):
    def __init__(self, session: AsyncSession):
        super().__init__(OriginalMediaFile, session)

    async def get_by_media_asset_id(
        self,
        media_asset_id: int,
    ) -> OriginalMediaFile | None:
        stmt = self._base_query().where(
            OriginalMediaFile.media_asset_id == media_asset_id
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_storage_key(
        self,
        storage_key: str,
    ) -> OriginalMediaFile | None:
        stmt = self._base_query().where(OriginalMediaFile.storage_key == storage_key)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_checksum(
        self,
        checksum: str,
    ) -> OriginalMediaFile | None:
        stmt = self._base_query().where(OriginalMediaFile.checksum == checksum)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ProcessingJobRepository(BaseRepository[ProcessingJob]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProcessingJob, session)

    async def get_by_media_asset(
        self,
        media_asset_id: int,
    ) -> list[ProcessingJob]:
        stmt = (
            self._base_query()
            .where(ProcessingJob.media_asset_id == media_asset_id)
            .order_by(ProcessingJob.created_at.desc())
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_jobs(
        self,
    ) -> list[ProcessingJob]:
        stmt = self._base_query().where(
            ProcessingJob.status.in_(
                [
                    ProcessingJobStatus.QUEUED,
                    ProcessingJobStatus.PROCESSING,
                ]
            )
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_failed_jobs(
        self,
    ) -> list[ProcessingJob]:
        stmt = self._base_query().where(
            ProcessingJob.status == ProcessingJobStatus.FAILED
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_media_asset_id(self, media_asset_id: int) -> list[ProcessingJob]:
        stmt = select(ProcessingJob).where(
            ProcessingJob.media_asset_id == media_asset_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_queued_jobs(self, limit: int = 10) -> list[ProcessingJob]:
        stmt = (
            select(ProcessingJob)
            .where(ProcessingJob.status == ProcessingJobStatus.QUEUED)
            .order_by(ProcessingJob.created_at)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class MediaRepresentationRepository(BaseRepository[MediaRepresentation]):
    def __init__(self, session: AsyncSession):
        super().__init__(MediaRepresentation, session)

    async def get_by_media_asset(
        self,
        media_asset_id: int,
    ) -> list[MediaRepresentation]:
        stmt = self._base_query().where(
            MediaRepresentation.media_asset_id == media_asset_id
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_quality(
        self,
        media_asset_id: int,
        quality: str,
    ) -> MediaRepresentation | None:
        stmt = self._base_query().where(
            MediaRepresentation.media_asset_id == media_asset_id,
            MediaRepresentation.quality == quality,
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_playlist_path(
        self,
        playlist_path: str,
    ) -> MediaRepresentation | None:
        stmt = self._base_query().where(
            MediaRepresentation.playlist_path == playlist_path
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class StreamingManifestRepository(BaseRepository[StreamingManifest]):
    def __init__(self, session: AsyncSession):
        super().__init__(StreamingManifest, session)

    async def get_by_media_asset(
        self,
        media_asset_id: int,
    ) -> list[StreamingManifest]:
        stmt = self._base_query().where(
            StreamingManifest.media_asset_id == media_asset_id
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_storage_key(
        self,
        storage_key: str,
    ) -> StreamingManifest | None:
        stmt = self._base_query().where(StreamingManifest.storage_key == storage_key)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class ThumbnailRepository(BaseRepository[Thumbnail]):
    def __init__(self, session: AsyncSession):
        super().__init__(Thumbnail, session)

    async def get_by_media_asset(
        self,
        media_asset_id: int,
    ) -> list[Thumbnail]:
        stmt = self._base_query().where(Thumbnail.media_asset_id == media_asset_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_storage_key(
        self,
        storage_key: str,
    ) -> Thumbnail | None:
        stmt = self._base_query().where(Thumbnail.storage_key == storage_key)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
