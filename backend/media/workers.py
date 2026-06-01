import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
import subprocess
import hashlib
import boto3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rq import get_current_job

# These imports will be resolved when the worker runs
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import get_settings
from utils.queue import queue_service

logger = logging.getLogger(__name__)
settings = get_settings()


def update_job_progress(progress: int):
    """Update job progress in Redis"""
    job = get_current_job()
    if job:
        queue_service.set_job_progress(job.id, progress)


def process_media_asset(
    asset_id: int, storage_key: str, media_type: str
) -> Dict[str, Any]:
    """
    Process media asset: generate thumbnails, transcoding, etc.
    This runs in a background RQ worker
    """
    job = get_current_job()
    logger.info(
        f"Processing {media_type} asset {asset_id} (Job: {job.id if job else 'unknown'})"
    )

    # Setup database connection
    engine = create_engine(settings.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Setup S3 client
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.RUSTFS_ENDPOINT,
        aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
        aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
        region_name="us-east-1",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    temp_file = None

    try:
        # Update status to PROCESSING
        from media.models import (
            MediaAsset,
            MediaAssetStatus,
            ProcessingJob,
            ProcessingJobStatus,
        )
        from media.repository import MediaAssetRepository, ProcessingJobRepository

        media_asset_repo = MediaAssetRepository(session)
        processing_job_repo = ProcessingJobRepository(session)

        # Get asset
        asset = await_in_sync(session, media_asset_repo.get_by_id, asset_id)
        if not asset:
            raise Exception(f"Asset {asset_id} not found")

        # Update processing job status
        processing_jobs = await_in_sync(
            session, processing_job_repo.get_by_media_asset_id, asset_id
        )
        for pj in processing_jobs:
            if pj.job_type.value == "transcode":
                pj.status = ProcessingJobStatus.PROCESSING
                break

        asset.status = MediaAssetStatus.PROCESSING
        session.commit()

        update_job_progress(10)

        # Download file temporarily
        update_job_progress(20)
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f"_{asset_id}.mp4"
        ) as tmp:
            temp_file = tmp.name
            s3_client.download_file(settings.RUSTFS_BUCKET_NAME, storage_key, temp_file)

        update_job_progress(30)

        if media_type == "video":
            # Process video
            result = process_video(asset_id, temp_file, s3_client, session)
        else:
            # Process audio
            result = process_audio(asset_id, temp_file, s3_client, session)

        update_job_progress(90)

        # Update asset status to READY
        asset.status = MediaAssetStatus.READY

        # Update processing job status to COMPLETED
        for pj in processing_jobs:
            if pj.job_type.value == "transcode":
                pj.status = ProcessingJobStatus.COMPLETED
                pj.progress = 100
                break

        session.commit()

        update_job_progress(100)

        logger.info(f"Successfully processed asset {asset_id}")
        return {
            "status": "success",
            "asset_id": asset_id,
            "media_type": media_type,
            "result": result,
        }

    except Exception as e:
        logger.error(f"Failed to process asset {asset_id}: {str(e)}", exc_info=True)

        # Update status to FAILED
        try:
            from media.models import (
                MediaAsset,
                MediaAssetStatus,
                ProcessingJob,
                ProcessingJobStatus,
            )

            asset = session.query(MediaAsset).filter(MediaAsset.id == asset_id).first()
            if asset:
                asset.status = MediaAssetStatus.FAILED

                # Update processing job
                processing_jobs = (
                    session.query(ProcessingJob)
                    .filter(ProcessingJob.media_asset_id == asset_id)
                    .all()
                )
                for pj in processing_jobs:
                    if pj.job_type.value == "transcode":
                        pj.status = ProcessingJobStatus.FAILED
                        pj.error_message = str(e)
                        break

                session.commit()
        except:
            pass

        raise e

    finally:
        # Clean up temp file
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)

        session.close()


def process_video(asset_id: int, video_path: str, s3_client, session) -> Dict[str, Any]:
    """Process video file"""
    update_job_progress(40)

    # Get video duration using ffprobe
    duration_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        video_path,
    ]
    duration = float(subprocess.check_output(duration_cmd).decode().strip())

    update_job_progress(50)

    # Generate thumbnails at different timestamps
    thumbnail_times = [1, 30, 60, 120]  # seconds
    thumbnails = []

    for i, time_sec in enumerate(thumbnail_times):
        if time_sec < duration:
            thumbnail_path = f"/tmp/thumb_{asset_id}_{i}.jpg"
            thumbnail_cmd = [
                "ffmpeg",
                "-i",
                video_path,
                "-ss",
                str(time_sec),
                "-vframes",
                "1",
                "-vf",
                "scale=320:-1",
                "-y",
                thumbnail_path,
            ]
            subprocess.run(thumbnail_cmd, capture_output=True, check=True)

            # Upload thumbnail to S3
            thumbnail_key = f"thumbnails/{asset_id}_{i}_{time_sec}s.jpg"
            with open(thumbnail_path, "rb") as f:
                s3_client.upload_fileobj(f, settings.RUSTFS_BUCKET_NAME, thumbnail_key)

            thumbnails.append(thumbnail_key)
            os.unlink(thumbnail_path)

        update_job_progress(50 + (i + 1) * 10)

    # Generate HLS segments (optional)
    hls_key = None
    if duration > 0:
        hls_key = f"hls/{asset_id}/playlist.m3u8"
        # HLS generation logic here...

    return {
        "duration": duration,
        "thumbnails": thumbnails,
        "hls_playlist": hls_key,
    }


def process_audio(asset_id: int, audio_path: str, s3_client, session) -> Dict[str, Any]:
    """Process audio file"""
    update_job_progress(40)

    # Get audio duration
    duration_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    duration = float(subprocess.check_output(duration_cmd).decode().strip())

    update_job_progress(60)

    # Generate waveform data
    waveform_cmd = [
        "ffmpeg",
        "-i",
        audio_path,
        "-filter_complex",
        "showwavespic=s=800x200:colors=blue",
        "-frames:v",
        "1",
        "-y",
        f"/tmp/waveform_{asset_id}.png",
    ]
    subprocess.run(waveform_cmd, capture_output=True, check=True)

    # Upload waveform
    waveform_key = f"waveforms/{asset_id}.png"
    with open(f"/tmp/waveform_{asset_id}.png", "rb") as f:
        s3_client.upload_fileobj(f, settings.RUSTFS_BUCKET_NAME, waveform_key)

    os.unlink(f"/tmp/waveform_{asset_id}.png")

    update_job_progress(80)

    return {
        "duration": duration,
        "waveform": waveform_key,
    }


def await_in_sync(session, async_func, *args, **kwargs):
    """Helper to call async function from sync context"""
    import asyncio

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        loop.close()
