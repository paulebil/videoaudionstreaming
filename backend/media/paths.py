from enum import Enum
from typing import Optional, Dict
from datetime import datetime
import re


class HLSQualities(str, Enum):
    """HLS quality levels with their configurations"""

    V1080P = "video_1080p"
    V720P = "video_720p"
    V480P = "video_480p"
    V360P = "video_360p"
    A128K = "audio_128k"
    A64K = "audio_64k"

    @property
    def is_video(self) -> bool:
        return self.value.startswith("video_")

    @property
    def is_audio(self) -> bool:
        return self.value.startswith("audio_")

    @property
    def bitrate(self) -> str:
        """Get recommended bitrate for this quality"""
        bitrates = {
            "video_1080p": "5000k",
            "video_720p": "2500k",
            "video_480p": "1000k",
            "video_360p": "500k",
            "audio_128k": "128k",
            "audio_64k": "64k",
        }
        return bitrates.get(self.value, "1000k")

    @property
    def resolution(self) -> Optional[tuple[int, int]]:
        """Get resolution for video qualities"""
        resolutions = {
            "video_1080p": (1920, 1080),
            "video_720p": (1280, 720),
            "video_480p": (854, 480),
            "video_360p": (640, 360),
        }
        return resolutions.get(self.value)


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    SUBTITLE = "subtitle"


class StorageTier(str, Enum):
    ORIGINAL = "original"
    PROCESSED = "processed"
    TEMP = "temp"
    ARCHIVE = "archive"


class MediaPaths:
    """
    Deterministic object storage key builder for media assets.

    Path structure:
    /{tenant}/{media_type}/{storage_tier}/{media_id}/{category}/{filename}

    Examples:
    - Original: media/video/original/{media_id}/source.mp4
    - Thumbnails: media/video/processed/{media_id}/thumbnails/cover.jpg
    - HLS: media/video/processed/{media_id}/hls/video_720p/index.m3u8
    """

    def __init__(
        self, media_id: str, media_type: str = "video", tenant: str = "default"
    ):
        """
        Initialize MediaPaths

        Args:
            media_id: Unique identifier for the media (UUID, slug, or ID)
            media_type: Type of media (video, audio, image, subtitle)
            tenant: Tenant identifier for multi-tenancy support
        """
        self.media_id = media_id
        self.media_type = media_type
        self.tenant = tenant

        # Sanitize media_id for safe path usage
        self.safe_media_id = self._sanitize_path_component(media_id)

    def _sanitize_path_component(self, component: str) -> str:
        """Sanitize a path component to be URL-safe"""
        # Replace any non-alphanumeric characters with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9\-_]", "_", component)
        return sanitized

    def base(self) -> str:
        """Base path for all media assets"""
        return f"{self.tenant}/{self.media_type}"

    def media_root(self) -> str:
        """Root path for specific media ID"""
        return f"{self.base()}/{self.safe_media_id}"

    def tier_path(self, tier: StorageTier) -> str:
        """Path for specific storage tier"""
        return f"{self.media_root()}/{tier.value}"

    def original(self, filename: str = "source") -> str:
        """
        Path for original uploaded file

        Args:
            filename: Original filename (extension will be preserved)

        Returns:
            Full storage path for original file
        """

        if "." not in filename:
            extension = self._get_default_extension()
            filename = f"{filename}{extension}"

        return f"{self.tier_path(StorageTier.ORIGINAL)}/{filename}"

    def _get_default_extension(self) -> str:
        """Get default file extension based on media type"""
        extensions = {
            "video": ".mp4",
            "audio": ".mp3",
            "image": ".jpg",
            "subtitle": ".vtt",
        }
        return extensions.get(self.media_type, ".bin")

    def processed_base(self) -> str:
        """Base path for processed files"""
        return self.tier_path(StorageTier.PROCESSED)

    def thumbnails_dir(self) -> str:
        """Directory for thumbnails"""
        return f"{self.processed_base()}/thumbnails"

    def thumbnail(self, filename: str = "cover.jpg") -> str:
        """Path for a specific thumbnail"""
        return f"{self.thumbnails_dir()}/{filename}"

    def thumbnail_at_time(self, timestamp: int, extension: str = "jpg") -> str:
        """Path for thumbnail at specific timestamp (in seconds)"""
        return f"{self.thumbnails_dir()}/{timestamp}s.{extension}"

    def sprite_sheet(self) -> str:
        """Path for thumbnail sprite sheet"""
        return f"{self.thumbnails_dir()}/sprite.jpg"

    def waveform_dir(self) -> str:
        """Directory for waveform images"""
        return f"{self.processed_base()}/waveforms"

    def waveform(self, format: str = "png") -> str:
        """Path for waveform image"""
        return f"{self.waveform_dir()}/waveform.{format}"

    def waveform_data(self) -> str:
        """Path for waveform JSON data"""
        return f"{self.waveform_dir()}/waveform.json"

    def transcoded_dir(self) -> str:
        """Directory for transcoded files"""
        return f"{self.processed_base()}/transcoded"

    def transcoded(self, quality: str, filename: str = "output.mp4") -> str:
        """Path for transcoded file at specific quality"""
        return f"{self.transcoded_dir()}/{quality}/{filename}"

    def streaming_base(self) -> str:
        """Base path for streaming assets"""
        return f"{self.processed_base()}/streaming"

    def hls_base(self) -> str:
        """Base path for HLS assets"""
        return f"{self.streaming_base()}/hls"

    def master_playlist(self) -> str:
        """Path for HLS master playlist"""
        return f"{self.hls_base()}/master.m3u8"

    def hls_quality_dir(self, quality: HLSQualities) -> str:
        """Directory for specific HLS quality"""
        return f"{self.hls_base()}/{quality.value}"

    def hls_playlist(self, quality: HLSQualities) -> str:
        """Path for HLS quality playlist"""
        return f"{self.hls_quality_dir(quality)}/index.m3u8"

    def hls_segment(self, quality: HLSQualities, segment_num: int) -> str:
        """Path for HLS segment"""
        return f"{self.hls_quality_dir(quality)}/segment_{segment_num:04d}.ts"

    def hls_segment_pattern(self, quality: HLSQualities) -> str:
        """Pattern for HLS segments (for m3u8 playlist)"""
        return f"{self.hls_quality_dir(quality)}/segment_%04d.ts"

    def hls_init_segment(self, quality: HLSQualities) -> str:
        """Path for HLS init segment (fMP4)"""
        return f"{self.hls_quality_dir(quality)}/init.mp4"

    def dash_base(self) -> str:
        """Base path for DASH assets"""
        return f"{self.streaming_base()}/dash"

    def dash_manifest(self) -> str:
        """Path for DASH manifest"""
        return f"{self.dash_base()}/manifest.mpd"

    def dash_quality_dir(self, quality: str) -> str:
        """Directory for specific DASH quality"""
        return f"{self.dash_base()}/{quality}"

    def dash_segment(self, quality: str, segment_num: int) -> str:
        """Path for DASH segment"""
        return f"{self.dash_quality_dir(quality)}/segment_{segment_num:04d}.m4s"

    def dash_init_segment(self, quality: str) -> str:
        """Path for DASH init segment"""
        return f"{self.dash_quality_dir(quality)}/init.mp4"

    def subtitles_dir(self) -> str:
        """Directory for subtitles"""
        return f"{self.processed_base()}/subtitles"

    def subtitle(self, lang: str, format: str = "vtt") -> str:
        """
        Path for subtitle file

        Args:
            lang: Language code (e.g., 'en', 'es', 'fr')
            format: Subtitle format (vtt, srt, ttml)
        """
        return f"{self.subtitles_dir()}/{lang}.{format}"

    def closed_captions(self, lang: str) -> str:
        """Path for closed captions (embedded)"""
        return f"{self.subtitles_dir()}/{lang}_cc.vtt"

    def metadata_dir(self) -> str:
        """Directory for metadata files"""
        return f"{self.processed_base()}/metadata"

    def info_json(self) -> str:
        """Path for media info JSON"""
        return f"{self.metadata_dir()}/info.json"

    def sprite_data(self) -> str:
        """Path for sprite data JSON (for seeking)"""
        return f"{self.metadata_dir()}/sprite_data.json"

    def chapter_marks(self) -> str:
        """Path for chapter markers"""
        return f"{self.metadata_dir()}/chapters.json"

    def temp(self, filename: str = "temp") -> str:
        """Path for temporary files during processing"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{self.tier_path(StorageTier.TEMP)}/{timestamp}_{filename}"

    def archive(self, filename: str) -> str:
        """Path for archived files"""
        return f"{self.tier_path(StorageTier.ARCHIVE)}/{filename}"

    def get_all_paths(self) -> Dict[str, str]:
        """Get all important paths for this media asset"""
        return {
            "original": self.original(),
            "thumbnails_dir": self.thumbnails_dir(),
            "master_playlist": self.master_playlist(),
            "hls_base": self.hls_base(),
            "subtitles_dir": self.subtitles_dir(),
            "metadata_dir": self.metadata_dir(),
            "waveform": self.waveform(),
            "info_json": self.info_json(),
        }

    def get_hls_qualities_paths(self) -> Dict[str, Dict[str, str]]:
        """Get paths for all HLS qualities"""
        qualities = {}
        for quality in HLSQualities:
            qualities[quality.value] = {
                "playlist": self.hls_playlist(quality),
                "dir": self.hls_quality_dir(quality),
                "segment_pattern": self.hls_segment_pattern(quality),
            }
        return qualities

    def __repr__(self) -> str:
        return f"MediaPaths(media_id={self.media_id}, media_type={self.media_type})"

    def __str__(self) -> str:
        return self.media_root()



def create_media_paths(asset) -> MediaPaths:
    """
    Helper to create MediaPaths from a MediaAsset object

    Args:
        asset: MediaAsset model instance

    Returns:
        MediaPaths instance
    """
    media_id = str(asset.base_uuid)

    media_type = (
        asset.media_type.value
        if hasattr(asset.media_type, "value")
        else str(asset.media_type)
    )

    return MediaPaths(media_id, media_type)
