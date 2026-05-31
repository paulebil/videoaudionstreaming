from fastapi import HTTPException, UploadFile, status
from core.settings import get_settings

settings = get_settings()


class FileValidator:
    """Validate uploaded files"""

    @staticmethod
    async def validate_media_file(file: UploadFile, media_type: str) -> None:
        """
        Validate file size and type based on media type
        """
        # Check file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        await file.seek(0)  # Reset position

        if media_type == "video":
            if file_size > settings.MAX_VIDEO_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Video file too large. Max size: {settings.MAX_VIDEO_SIZE // (1024*1024)}MB",
                )
            if file.content_type not in settings.ALLOWED_VIDEO_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported video type. Allowed: {settings.ALLOWED_VIDEO_TYPES}",
                )
        elif media_type == "audio":
            if file_size > settings.MAX_AUDIO_SIZE:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Audio file too large. Max size: {settings.MAX_AUDIO_SIZE // (1024*1024)}MB",
                )
            if file.content_type not in settings.ALLOWED_AUDIO_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported audio type. Allowed: {settings.ALLOWED_AUDIO_TYPES}",
                )

    @staticmethod
    def validate_title(title: str) -> None:
        """Validate title"""
        if not title or len(title.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Title cannot be empty"
            )
        if len(title) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Title too long (max 500 characters)",
            )
