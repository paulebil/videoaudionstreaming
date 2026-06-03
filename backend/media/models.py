from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
    Boolean,
)
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from utils.models import BaseUtilityModel, SoftDeleteMixin

class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class MediaAssetStatus(str, Enum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class ProcessingJobType(str, Enum):
    TRANSCODE = "transcode"
    THUMBNAIL = "thumbnail"
    WAVEFORM = "waveform"
    SUBTITLE = "subtitle"


class ProcessingJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SegmentType(str, Enum):
    TS = "ts"
    FMP4 = "fmp4"


class ManifestType(str, Enum):
    HLS = "hls"
    DASH = "dash"


class MediaAsset(BaseUtilityModel):
    __tablename__ = "media_assets"
    __abstract__ = False

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        index=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    media_type: Mapped[MediaType] = mapped_column(
        SAEnum(
            MediaType,
            name="media_type_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[MediaAssetStatus] = mapped_column(
        SAEnum(
            MediaAssetStatus,
            name="media_asset_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=MediaAssetStatus.UPLOADED,
        server_default=text("'uploaded'"),
        index=True,
    )

    duration_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    original_file: Mapped["OriginalMediaFile"] = relationship(
        "OriginalMediaFile",
        back_populates="media_asset",
        uselist=False,
        cascade="all, delete-orphan",
    )

    processing_jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob",
        back_populates="media_asset",
        cascade="all, delete-orphan",
    )

    representations: Mapped[list["MediaRepresentation"]] = relationship(
        "MediaRepresentation",
        back_populates="media_asset",
        cascade="all, delete-orphan",
    )

    manifests: Mapped[list["StreamingManifest"]] = relationship(
        "StreamingManifest",
        back_populates="media_asset",
        cascade="all, delete-orphan",
    )

    thumbnails: Mapped[list["Thumbnail"]] = relationship(
        "Thumbnail",
        back_populates="media_asset",
        cascade="all, delete-orphan",
    )

    __slug_source_field__ = "title"

    __search_fields__ = [
        "title",
        "description",
    ]

    __ordering_fields__ = [
        "title",
        "created_at",
    ]

    __filterable_fields__ = [
        "media_type",
        "status",
        "title",
    ]

    @declared_attr.directive
    def __table_args__(cls):
        return (
            CheckConstraint(
                "duration_seconds IS NULL OR duration_seconds >= 0",
                name="ck_media_assets_duration_non_negative",
            ),
            {"schema": "public"},
        )


class OriginalMediaFile(BaseUtilityModel):
    __tablename__ = "original_media_files"
    __abstract__ = False

    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    storage_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
    )

    filename: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    content_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    size_bytes: Mapped[int] = mapped_column(
        BIGINT,
        nullable=False,
    )

    checksum: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )

    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        back_populates="original_file",
    )

    __slug_source_field__ = "filename"

    @declared_attr.directive
    def __table_args__(cls):
        return (
            CheckConstraint(
                "size_bytes >= 0",
                name="ck_original_media_files_size_non_negative",
            ),
            {"schema": "public"},
        )


class ProcessingJob(SoftDeleteMixin):
    __tablename__ = "processing_jobs"
    __abstract__ = False

    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    job_type: Mapped[ProcessingJobType] = mapped_column(
        SAEnum(
            ProcessingJobType,
            name="processing_job_type_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[ProcessingJobStatus] = mapped_column(
        SAEnum(
            ProcessingJobStatus,
            name="processing_job_status_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=ProcessingJobStatus.QUEUED,
        server_default=text("'queued'"),
        index=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        back_populates="processing_jobs",
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            CheckConstraint(
                "progress BETWEEN 0 AND 100",
                name="ck_processing_jobs_progress_range",
            ),
            Index(
                "ix_processing_jobs_media_asset_status",
                "media_asset_id",
                "status",
            ),
            {"schema": "public"},
        )


class MediaRepresentation(SoftDeleteMixin):
    __tablename__ = "media_representations"
    __abstract__ = False

    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    quality: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    codec: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    bitrate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    segment_type: Mapped[SegmentType] = mapped_column(
        SAEnum(
            SegmentType,
            name="segment_type_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        default=SegmentType.FMP4,
        server_default=text("'fmp4'"),
    )

    playlist_path: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
    )

    is_master: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    resolution: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        back_populates="representations",
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            CheckConstraint(
                "bitrate > 0",
                name="ck_media_representations_bitrate_positive",
            ),
            CheckConstraint(
                "width IS NULL OR width > 0",
                name="ck_media_representations_width_positive",
            ),
            CheckConstraint(
                "height IS NULL OR height > 0",
                name="ck_media_representations_height_positive",
            ),
            Index(
                "ix_media_representations_media_quality",
                "media_asset_id",
                "quality",
            ),
            {"schema": "public"},
        )


class StreamingManifest(SoftDeleteMixin):
    __tablename__ = "streaming_manifests"
    __abstract__ = False

    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    manifest_type: Mapped[ManifestType] = mapped_column(
        SAEnum(
            ManifestType,
            name="manifest_type_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )

    storage_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
    )

    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        back_populates="manifests",
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            {"schema": "public"},
        )


class Thumbnail(SoftDeleteMixin):
    __tablename__ = "thumbnails"
    __abstract__ = False

    media_asset_id: Mapped[int] = mapped_column(
        ForeignKey(
            "public.media_assets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    storage_key: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        unique=True,
    )

    width: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    height: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    media_asset: Mapped["MediaAsset"] = relationship(
        "MediaAsset",
        back_populates="thumbnails",
    )

    @declared_attr.directive
    def __table_args__(cls):
        return (
            CheckConstraint(
                "width > 0",
                name="ck_thumbnails_width_positive",
            ),
            CheckConstraint(
                "height > 0",
                name="ck_thumbnails_height_positive",
            ),
            {"schema": "public"},
        )
