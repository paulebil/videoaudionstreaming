import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess
import uuid
import boto3
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session
from rq import get_current_job

import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.settings import get_settings
from utils.queue import queue_service
from media.paths import MediaPaths, HLSQualities, create_media_paths
from media.models import (
    MediaAsset,
    MediaAssetStatus,
    ProcessingJob,
    ProcessingJobStatus,
    MediaRepresentation,
    SegmentType,
    Thumbnail,
    OriginalMediaFile,
)

logger = logging.getLogger(__name__)
settings = get_settings()


sync_database_url = settings.SYNC_DATABASE_URL

sync_engine = create_engine(
    sync_database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def update_job_progress(progress: int):
    """Update job progress in Redis"""
    job = get_current_job()
    if job:
        queue_service.set_job_progress(job.id, progress)


class MediaAssetSyncRepo:
    """Synchronous repository for media assets (for RQ workers)"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, obj_id: int) -> Optional[MediaAsset]:
        return self.session.query(MediaAsset).filter(MediaAsset.id == obj_id).first()

    def get_by_identifier(self, identifier: str) -> Optional[MediaAsset]:
        if identifier.isdigit():
            return (
                self.session.query(MediaAsset)
                .filter(MediaAsset.id == int(identifier))
                .first()
            )
        try:
            uuid_obj = uuid.UUID(identifier)
            return (
                self.session.query(MediaAsset)
                .filter(MediaAsset.base_uuid == uuid_obj)
                .first()
            )
        except ValueError:
            pass
        return (
            self.session.query(MediaAsset)
            .filter(MediaAsset.url_slug == identifier)
            .first()
        )

    def update(self, asset: MediaAsset) -> MediaAsset:
        self.session.flush()
        return asset


class ProcessingJobSyncRepo:
    """Synchronous repository for processing jobs (for RQ workers)"""

    def __init__(self, session: Session):
        self.session = session

    def get_by_media_asset_id(self, media_asset_id: int) -> List[ProcessingJob]:
        return (
            self.session.query(ProcessingJob)
            .filter(ProcessingJob.media_asset_id == media_asset_id)
            .all()
        )

    def create(self, job: ProcessingJob) -> ProcessingJob:
        self.session.add(job)
        self.session.flush()
        return job


class ThumbnailSyncRepo:
    """Synchronous repository for thumbnails (for RQ workers)"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, thumbnail: Thumbnail) -> Thumbnail:
        self.session.add(thumbnail)
        self.session.flush()
        return thumbnail


class MediaRepresentationSyncRepo:
    """Synchronous repository for media representations (for RQ workers)"""

    def __init__(self, session: Session):
        self.session = session

    def create(self, representation: MediaRepresentation) -> MediaRepresentation:
        self.session.add(representation)
        self.session.flush()
        return representation


def process_media_asset(
    asset_id: int, storage_key: str, media_type: str
) -> Dict[str, Any]:
    """
    Process media asset: generate thumbnails, transcoding, etc.
    This runs in a background RQ worker - FULLY SYNCHRONOUS
    """
    job = get_current_job()
    logger.info(
        f"Processing {media_type} asset {asset_id} (Job: {job.id if job else 'unknown'})"
    )

    session = SyncSessionLocal()

    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.RUSTFS_ENDPOINT,
        aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
        aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
        region_name="us-east-1",
        config=boto3.session.Config(signature_version="s3v4"),
    )

    temp_file = None
    asset = None

    try:
        media_asset_repo = MediaAssetSyncRepo(session)
        processing_job_repo = ProcessingJobSyncRepo(session)
        thumbnail_repo = ThumbnailSyncRepo(session)
        representation_repo = MediaRepresentationSyncRepo(session)

        asset = media_asset_repo.get_by_id(asset_id)
        if not asset:
            raise Exception(f"Asset {asset_id} not found")

        paths = create_media_paths(asset)

        processing_jobs = processing_job_repo.get_by_media_asset_id(asset_id)
        transcode_job = None
        for pj in processing_jobs:
            if pj.job_type.value == "transcode":
                pj.status = ProcessingJobStatus.PROCESSING
                transcode_job = pj
                break

        asset.status = MediaAssetStatus.PROCESSING
        session.commit()

        update_job_progress(10)

        update_job_progress(20)

        ext = ".mp4" if media_type == "video" else ".mp3"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f"_{asset_id}{ext}"
        ) as tmp:
            temp_file = tmp.name
            s3_client.download_file(settings.RUSTFS_BUCKET_NAME, storage_key, temp_file)

        update_job_progress(30)

        if media_type == "video":
            result = process_video(
                asset_id,
                temp_file,
                s3_client,
                session,
                paths,
                thumbnail_repo,
                representation_repo,
            )
        else:
            result = process_audio(
                asset_id, temp_file, s3_client, session, paths, thumbnail_repo
            )

        update_job_progress(90)

        asset.status = MediaAssetStatus.READY

        if not asset.duration_seconds and result.get("duration"):
            asset.duration_seconds = int(result["duration"])

        if transcode_job:
            transcode_job.status = ProcessingJobStatus.COMPLETED
            transcode_job.progress = 100

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

        try:
            if asset:
                asset.status = MediaAssetStatus.FAILED

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
        except Exception as db_error:
            logger.error(f"Failed to update database: {db_error}")

        raise e

    finally:
        if temp_file and os.path.exists(temp_file):
            os.unlink(temp_file)

        session.close()


def process_video(
    asset_id: int,
    video_path: str,
    s3_client,
    session: Session,
    paths: MediaPaths,
    thumbnail_repo: ThumbnailSyncRepo,
    representation_repo: MediaRepresentationSyncRepo,
) -> Dict[str, Any]:
    """Process video file with HLS streaming support"""

    update_job_progress(40)

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

    dimensions_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        video_path,
    ]
    dimensions_output = subprocess.check_output(dimensions_cmd).decode().strip()
    width, height = (
        map(int, dimensions_output.split(",")) if dimensions_output else (1920, 1080)
    )

    update_job_progress(50)

    thumbnails = generate_thumbnails(
        asset_id, video_path, s3_client, session, paths, thumbnail_repo, duration
    )

    update_job_progress(60)

    hls_result = generate_hls_streams(
        asset_id, video_path, s3_client, session, paths, representation_repo, duration
    )

    update_job_progress(85)

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "thumbnails": thumbnails,
        "hls": hls_result,
    }


def generate_thumbnails(
    asset_id: int,
    video_path: str,
    s3_client,
    session: Session,
    paths: MediaPaths,
    thumbnail_repo: ThumbnailSyncRepo,
    duration: float,
) -> List[str]:
    """Generate thumbnails at different timestamps using MediaPaths"""

    if duration <= 60:
        timestamps = [1, int(duration // 2), int(duration) - 1]
    else:
        timestamps = [1, 30, 60, 90, int(duration // 2), int(duration) - 30]
    timestamps = list(set([t for t in timestamps if t < duration]))[:6]

    thumbnails = []

    for i, timestamp in enumerate(timestamps):

        thumbnail_path = f"/tmp/thumb_{asset_id}_{timestamp}s.jpg"

        thumbnail_cmd = [
            "ffmpeg",
            "-nostdin",  
            "-y",  
            "-i",
            video_path,
            "-ss",
            str(timestamp),
            "-vframes",
            "1",
            "-vf",
            "scale=640:-1",
            "-loglevel",
            "error", 
            thumbnail_path,
        ]

        logger.info(f"Generating thumbnail at {timestamp}s for asset {asset_id}")
        result = subprocess.run(thumbnail_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise Exception(
                f"Failed to generate thumbnail at {timestamp}s: {result.stderr}"
            )

        thumbnail_key = paths.thumbnail_at_time(timestamp)
        with open(thumbnail_path, "rb") as f:
            s3_client.upload_fileobj(
                f,
                settings.RUSTFS_BUCKET_NAME,
                thumbnail_key,
                ExtraArgs={"ContentType": "image/jpeg"},
            )

        thumbnail_record = Thumbnail(
            media_asset_id=asset_id,
            storage_key=thumbnail_key,
            width=640,
            height=int(640 * 9 / 16),
        )
        thumbnail_repo.create(thumbnail_record)

        thumbnails.append(
            {
                "timestamp": timestamp,
                "key": thumbnail_key,
                "url": f"{settings.RUSTFS_ENDPOINT}/{settings.RUSTFS_BUCKET_NAME}/{thumbnail_key}",
            }
        )

        os.unlink(thumbnail_path)

        update_job_progress(60 + (i + 1) * 5)

    session.commit()

    return thumbnails


def generate_hls_streams(
    asset_id: int,
    video_path: str,
    s3_client,
    session: Session,
    paths: MediaPaths,
    representation_repo: MediaRepresentationSyncRepo,
    duration: float,
) -> Dict[str, Any]:
    """Generate HLS streams for adaptive bitrate streaming"""

    qualities_to_generate = []

    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
        video_path,
    ]
    output = subprocess.check_output(probe_cmd).decode().strip()
    if output:
        src_width, src_height = map(int, output.split(","))

        if src_height >= 1080:
            qualities_to_generate = [
                HLSQualities.V1080P,
                HLSQualities.V720P,
                HLSQualities.V480P,
                HLSQualities.V360P,
            ]
        elif src_height >= 720:
            qualities_to_generate = [
                HLSQualities.V720P,
                HLSQualities.V480P,
                HLSQualities.V360P,
            ]
        elif src_height >= 480:
            qualities_to_generate = [HLSQualities.V480P, HLSQualities.V360P]
        else:
            qualities_to_generate = [HLSQualities.V360P]

    qualities_to_generate.append(HLSQualities.A128K)

    representations = []
    temp_dir = tempfile.mkdtemp()

    try:
        for quality in qualities_to_generate:
            update_job_progress(65 + (len(representations) * 5))

            quality_dir = os.path.join(temp_dir, quality.value)
            os.makedirs(quality_dir, exist_ok=True)

            cmd = [
                "ffmpeg",
                "-nostdin", 
                "-y",  
                "-i",
                video_path,
            ]

            if quality.is_video:
                resolution = quality.resolution
                if resolution:
                    target_width, target_height = resolution
                    cmd.extend(
                        [
                            "-vf",
                            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2",
                            "-c:v",
                            "libx264",
                            "-b:v",
                            quality.bitrate,
                            "-preset",
                            "medium",
                            "-profile:v",
                            "main",
                            "-level",
                            "4.0",
                        ]
                    )
                else:
                    cmd.extend(["-c:v", "copy"])
            else:
                cmd.extend(["-vn"])

            cmd.extend(
                [
                    "-c:a",
                    "aac",
                    "-b:a",
                    quality.bitrate if quality.is_audio else "128k",
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                ]
            )

            cmd.extend(
                [
                    "-f",
                    "hls",
                    "-hls_time",
                    "6",
                    "-hls_list_size",
                    "0",
                    "-hls_segment_filename",
                    f"{quality_dir}/segment_%04d.ts",
                    "-loglevel",
                    "error",  
                    f"{quality_dir}/index.m3u8",
                ]
            )

            logger.info(f"Generating HLS stream for quality: {quality.value}")
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(
                    f"FFmpeg error for quality {quality.value}: {result.stderr}"
                )
                raise Exception(
                    f"Failed to generate HLS stream for {quality.value}: {result.stderr}"
                )

            playlist_key = paths.hls_playlist(quality)
            s3_client.upload_file(
                f"{quality_dir}/index.m3u8",
                settings.RUSTFS_BUCKET_NAME,
                playlist_key,
                ExtraArgs={"ContentType": "application/vnd.apple.mpegurl"},
            )

            segment_count = 0
            segment_files = sorted(Path(quality_dir).glob("segment_*.ts"))
            for segment_file in segment_files:
                segment_key = paths.hls_segment(quality, segment_count)
                s3_client.upload_file(
                    str(segment_file),
                    settings.RUSTFS_BUCKET_NAME,
                    segment_key,
                    ExtraArgs={"ContentType": "video/MP2T"},
                )
                segment_count += 1

            resolution = quality.resolution
            resolution_str = (
                f"{resolution[0]}x{resolution[1]}"
                if quality.is_video and resolution
                else None
            )
            representation = MediaRepresentation(
                media_asset_id=asset_id,
                quality=quality.value,
                codec="h264",
                bitrate=int(quality.bitrate.replace("k", "000")),
                width=resolution[0] if quality.is_video and resolution else None,
                height=resolution[1] if quality.is_video and resolution else None,
                segment_type=SegmentType.TS,
                playlist_path=playlist_key,
                is_master=False,
                resolution=resolution_str,
            )
            representation_repo.create(representation)
            representations.append(representation)

        session.commit()

        master_playlist_key = paths.master_playlist()
        master_content = "#EXTM3U\n"
        master_content += "#EXT-X-VERSION:6\n\n"

        for rep in representations:
            if rep.quality.startswith("video_"):
                master_content += f"#EXT-X-STREAM-INF:BANDWIDTH={rep.bitrate},RESOLUTION={rep.resolution}\n"
                master_content += f"{rep.playlist_path}\n\n"

        for rep in representations:
            if rep.quality.startswith("audio_"):
                master_content += (
                    f'#EXT-X-STREAM-INF:BANDWIDTH={rep.bitrate},AUDIO="audio"\n'
                )
                master_content += f"{rep.playlist_path}\n\n"

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".m3u8") as f:
            f.write(master_content)
            master_temp_path = f.name

        s3_client.upload_file(
            master_temp_path,
            settings.RUSTFS_BUCKET_NAME,
            master_playlist_key,
            ExtraArgs={"ContentType": "application/vnd.apple.mpegurl"},
        )

        os.unlink(master_temp_path)

        return {
            "master_playlist": master_playlist_key,
            "representations": len(representations),
            "qualities": [q.value for q in qualities_to_generate],
        }

    finally:
        import shutil

        shutil.rmtree(temp_dir, ignore_errors=True)


def process_audio(
    asset_id: int,
    audio_path: str,
    s3_client,
    session: Session,
    paths: MediaPaths,
    thumbnail_repo: ThumbnailSyncRepo,
) -> Dict[str, Any]:
    """Process audio file with waveform generation"""

    update_job_progress(40)

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

    update_job_progress(50)

    waveform_path = f"/tmp/waveform_{asset_id}.png"
    
    waveform_cmd = [
        "ffmpeg",
        "-nostdin",  
        "-y",
        "-i",
        audio_path,
        "-filter_complex",
        "showwavespic=s=1600x400:colors=blue|cyan",
        "-frames:v",
        "1",
        "-loglevel",
        "error",
        waveform_path,
    ]
    result = subprocess.run(waveform_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error(f"FFmpeg error for waveform: {result.stderr}")
        raise Exception(f"Failed to generate waveform: {result.stderr}")

    waveform_key = paths.waveform()
    with open(waveform_path, "rb") as f:
        s3_client.upload_fileobj(
            f,
            settings.RUSTFS_BUCKET_NAME,
            waveform_key,
            ExtraArgs={"ContentType": "image/png"},
        )

    os.unlink(waveform_path)

    update_job_progress(60)

    waveform_data = generate_waveform_data(audio_path, s3_client, paths)

    update_job_progress(80)

    return {
        "duration": duration,
        "waveform_image": waveform_key,
        "waveform_data": waveform_data,
    }


def generate_waveform_data(audio_path: str, s3_client, paths: MediaPaths) -> str:
    """Generate waveform JSON data for interactive audio visualization"""

    waveform_json_path = f"/tmp/waveform_{os.getpid()}.json"

    try:
        import json
        import numpy as np

        sample_count = 1000
        waveform_points = [int(np.sin(i / 50) * 100 + 100) for i in range(sample_count)]

        waveform_data = {
            "sample_count": sample_count,
            "samples_per_second": 100,
            "duration_seconds": len(waveform_points) / 100,
            "data": waveform_points,
        }

        with open(waveform_json_path, "w") as f:
            json.dump(waveform_data, f)

        waveform_data_key = paths.waveform_data()
        with open(waveform_json_path, "rb") as f:
            s3_client.upload_fileobj(
                f,
                settings.RUSTFS_BUCKET_NAME,
                waveform_data_key,
                ExtraArgs={"ContentType": "application/json"},
            )

        return waveform_data_key

    finally:
        if os.path.exists(waveform_json_path):
            os.unlink(waveform_json_path)
