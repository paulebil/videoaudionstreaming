from fastapi import HTTPException, status
from fastapi_pagination.ext.sqlalchemy import paginate

from .models import MediaAsset
from .repository import MediaAssetRepository, OriginalMediaFileRepository
from .schemas import (
    MediaAssetCreate,
    MediaAssetUpdate,
    MediaAssetListFilters,
    MediaAssetResponse,
)


class MediaAssetService:

    def __init__(
        self,
        media_asset_repository: MediaAssetRepository,
        original_file_repository: OriginalMediaFileRepository,
    ):
        self.media_asset_repository = media_asset_repository
        self.original_file_repository = original_file_repository


    async def _generate_file_url(self, storage_key: str) -> str:
        """
        Replace this with RustFS / MinIO presigned URL generator.
        """
        return f"https://storage.example.com/{storage_key}?presigned=true"

    def get_filtered_statement(self, filters: MediaAssetListFilters):
        return self.media_asset_repository.build_query(
            search=filters.search,
            full_text_search=filters.full_text_search,
            filters=filters.to_repository_filters() or None,
            ordering=filters.ordering,
        )

    async def list_media_assets(self, filters: MediaAssetListFilters):
        stmt = self.get_filtered_statement(filters)
        return await paginate(self.media_asset_repository.session, stmt)


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
            file_url = await self._generate_file_url(original_file.storage_key)

        return MediaAssetResponse.model_validate(
            media_asset,
            from_attributes=True,
        ).model_copy(update={"file_url": file_url})


    async def create_media_asset(self, data: MediaAssetCreate):
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

        return MediaAssetResponse.model_validate(created)


    async def create_media_assets(self, data_list: list[MediaAssetCreate]):
        titles = [d.title for d in data_list]

        stmt = self.media_asset_repository.build_query(filters={"title__in": titles})

        result = await self.media_asset_repository.session.execute(stmt)
        existing = result.scalars().all()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Some media assets already exist.",
            )

        assets = [MediaAsset(**data.model_dump()) for data in data_list]

        created = await self.media_asset_repository.create_many(assets)

        await self.media_asset_repository.session.commit()

        for item in created:
            await self.media_asset_repository.session.refresh(item)

        return [MediaAssetResponse.model_validate(item) for item in created]


    async def update_media_asset(self, identifier: str, data: MediaAssetUpdate):
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

        for k, v in data.model_dump(exclude_unset=True).items():
            setattr(media_asset, k, v)

        updated = await self.media_asset_repository.update(media_asset)

        await self.media_asset_repository.session.commit()
        await self.media_asset_repository.session.refresh(updated)

        return MediaAssetResponse.model_validate(updated)


    async def delete_media_asset(self, identifier: str, hard: bool = False):
        deleted = await self.media_asset_repository.delete_media_asset(
            identifier=identifier,
            hard=hard,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Media asset not found.",
            )

        await self.media_asset_repository.session.commit()
