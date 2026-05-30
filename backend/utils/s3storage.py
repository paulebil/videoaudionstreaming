from abc import ABC, abstractmethod
from typing import BinaryIO, Dict

from fastapi.concurrency import run_in_threadpool
import boto3

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.settings import get_settings

settings = get_settings()


class StorageService(ABC):

    @abstractmethod
    def ensure_bucket(self, bucket: str) -> None:
        pass

    @abstractmethod
    def upload_file(
        self, bucket: str, key: str, file_obj: BinaryIO, content_type: str
    ) -> Dict:
        pass

    @abstractmethod
    def generate_presigned_url(self, bucket: str, key: str, expires: int = 3600) -> str:
        pass

    @abstractmethod
    def download_file(self, bucket: str, key: str, file_path: str) -> str:
        pass


class S3StorageService(StorageService):

    def __init__(self):

        self.internal_client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            region_name="us-east-1",
            config=boto3.session.Config(s3={"addressing_style": "path"}),
        )

        self.external_client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            region_name="us-east-1",
            config=boto3.session.Config(s3={"addressing_style": "path"}),
        )

        self.default_bucket = settings.RUSTFS_BUCKET_NAME

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.internal_client.head_bucket(Bucket=bucket)
        except Exception:
            self.internal_client.create_bucket(Bucket=bucket)

    def upload_file(
        self, bucket: str, key: str, file_obj: BinaryIO, content_type: str
    ) -> Dict:

        bucket = bucket or self.default_bucket
        self.ensure_bucket(bucket)

        self.internal_client.upload_fileobj(
            Fileobj=file_obj,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )

        return {
            "bucket": bucket,
            "key": key,
        }

    def generate_presigned_url(self, bucket: str, key: str, expires: int = 3600) -> str:

        bucket = bucket or self.default_bucket

        return self.external_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires
        )

    def download_file(self, bucket: str, key: str, file_path: str) -> str:

        bucket = bucket or self.default_bucket

        self.internal_client.download_file(bucket, key, file_path)
        return file_path


class AsyncStorageService:

    def __init__(self, sync_storage: S3StorageService):
        self.storage = sync_storage

    async def ensure_bucket(self, bucket: str) -> None:
        return await run_in_threadpool(self.storage.ensure_bucket, bucket)

    async def upload_file(
        self, bucket: str, key: str, file_obj: BinaryIO, content_type: str
    ) -> Dict:

        return await run_in_threadpool(
            self.storage.upload_file, bucket, key, file_obj, content_type
        )

    async def generate_presigned_url(
        self, bucket: str, key: str, expires: int = 3600
    ) -> str:

        return await run_in_threadpool(
            self.storage.generate_presigned_url, bucket, key, expires
        )

    async def download_file(self, bucket: str, key: str, file_path: str) -> str:

        return await run_in_threadpool(
            self.storage.download_file, bucket, key, file_path
        )

