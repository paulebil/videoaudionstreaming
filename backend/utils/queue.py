from redis import Redis
from rq import Queue
from rq.job import Job
from rq.registry import FinishedJobRegistry, FailedJobRegistry, StartedJobRegistry
from typing import Optional, Dict, Any
import json
import logging

from core.settings import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()

redis_conn = Redis.from_url(settings.REDIS_URL, decode_responses=True)

media_queue = Queue(
    "media",
    connection=redis_conn,
    default_timeout=3600,  
)

thumbnail_queue = Queue(
    "thumbnails",
    connection=redis_conn,
    default_timeout=1800,  
)

waveform_queue = Queue(
    "waveform",
    connection=redis_conn,
    default_timeout=900,  
)


class QueueService:
    """Service for managing RQ queues"""

    def __init__(self):
        self.redis_conn = redis_conn
        self.queues = {
            "media": media_queue,
            "thumbnails": thumbnail_queue,
            "waveform": waveform_queue,
        }

    def enqueue_media_processing(
        self, asset_id: int, storage_key: str, media_type: str, job_timeout: int = 3600
    ) -> Optional[Job]:
        """
        Enqueue a media processing job

        Args:
            asset_id: Media asset ID
            storage_key: S3 storage key
            media_type: 'video' or 'audio'
            job_timeout: Job timeout in seconds

        Returns:
            RQ Job object
        """
        from media.workers import process_media_asset

        try:
            job = media_queue.enqueue(
                process_media_asset,
                args=(asset_id, storage_key, media_type),
                job_timeout=job_timeout,
                result_ttl=86400,  
                failure_ttl=86400,  
                retry=3,  
                description=f"Process {media_type} asset {asset_id}",
            )
            return job
        except Exception as e:
            logger.error(f"Failed to enqueue job for asset {asset_id}: {str(e)}")
            return None

    def enqueue_thumbnail_generation(
        self, asset_id: int, storage_key: str, timestamps: list[str]
    ) -> Optional[Job]:
        """Enqueue thumbnail generation job"""
        from media.workers import generate_thumbnails

        try:
            job = thumbnail_queue.enqueue(
                generate_thumbnails,
                args=(asset_id, storage_key, timestamps),
                job_timeout=1800,
                result_ttl=86400,
                failure_ttl=86400,
            )
            return job
        except Exception as e:
            logger.error(
                f"Failed to enqueue thumbnail job for asset {asset_id}: {str(e)}"
            )
            return None

    def enqueue_waveform_generation(
        self, asset_id: int, storage_key: str
    ) -> Optional[Job]:
        """Enqueue waveform generation job for audio"""
        from media.workers import generate_waveform

        try:
            job = waveform_queue.enqueue(
                generate_waveform,
                args=(asset_id, storage_key),
                job_timeout=900,
                result_ttl=86400,
                failure_ttl=86400,
            )
            return job
        except Exception as e:
            logger.error(
                f"Failed to enqueue waveform job for asset {asset_id}: {str(e)}"
            )
            return None

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get status of a job"""
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)

            return {
                "job_id": job.id,
                "status": job.get_status(),
                "result": job.result if job.is_finished else None,
                "error": str(job.exc_info) if job.is_failed else None,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "enqueued_at": job.enqueued_at.isoformat() if job.enqueued_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "description": job.description,
                "progress": self._get_job_progress(job_id),
            }
        except Exception as e:
            return {"job_id": job_id, "status": "not_found", "error": str(e)}

    def _get_job_progress(self, job_id: str) -> int:
        """Get job progress from Redis (if set by worker)"""
        progress_key = f"job:{job_id}:progress"
        progress = self.redis_conn.get(progress_key)
        return int(progress) if progress else 0

    def set_job_progress(self, job_id: str, progress: int):
        """Set job progress in Redis"""
        progress_key = f"job:{job_id}:progress"
        self.redis_conn.setex(progress_key, 3600, progress)  

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get statistics for all queues"""
        stats = {}
        for name, queue in self.queues.items():
            stats[name] = {
                "count": queue.count,
                "is_empty": queue.is_empty,
                "jobs": [job.id for job in queue.get_jobs()[:10]], 
            }
        return stats

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job if it's not already finished"""
        try:
            job = Job.fetch(job_id, connection=self.redis_conn)
            if job.get_status() in ["queued", "started"]:
                job.cancel()
                return True
            return False
        except Exception:
            return False


queue_service = QueueService()
