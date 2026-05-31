from abc import ABC, abstractmethod
from typing import BinaryIO, Dict, Optional
from fastapi.concurrency import run_in_threadpool
import boto3
from botocore.exceptions import ClientError
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
    def copy_file(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> Dict:
        """Copy a file from one location to another within the storage"""
        pass

    @abstractmethod
    def generate_presigned_url(
        self, bucket: str, key: str, expires: int = 3600, method: str = "get_object"
    ) -> str:
        pass

    @abstractmethod
    def download_file(self, bucket: str, key: str, file_path: str) -> str:
        pass

    @abstractmethod
    def delete_file(self, bucket: str, key: str) -> bool:
        pass


class S3StorageService(StorageService):

    def __init__(self):

        s3_config = {
            "signature_version": "s3v4",
            "s3": {
                "addressing_style": "path",
            },
        }

        config = boto3.session.Config(**s3_config)

        self.internal_client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            region_name="us-east-1",
            config=config,
        )

        self.external_client = boto3.client(
            "s3",
            endpoint_url=settings.RUSTFS_ENDPOINT,
            aws_access_key_id=settings.RUSTFS_ACCESS_KEY,
            aws_secret_access_key=settings.RUSTFS_SECRET_KEY,
            region_name="us-east-1",
            config=config,
        )

        self.default_bucket = settings.RUSTFS_BUCKET_NAME

    def ensure_bucket(self, bucket: str) -> None:
        """Ensure bucket exists, create if it doesn't"""
        bucket = bucket or self.default_bucket
        try:
            self.internal_client.head_bucket(Bucket=bucket)
        except ClientError:
            self.internal_client.create_bucket(Bucket=bucket)
        except Exception as e:
            raise Exception(f"Failed to ensure bucket {bucket}: {str(e)}")

    def upload_file(
        self, bucket: str, key: str, file_obj: BinaryIO, content_type: str
    ) -> Dict:
        """Upload a file to S3/RustFS"""
        bucket = bucket or self.default_bucket
        self.ensure_bucket(bucket)

        try:
            self.internal_client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=bucket,
                Key=key,
                ExtraArgs={"ContentType": content_type},
            )
        except Exception as e:
            raise Exception(f"Failed to upload file {key} to bucket {bucket}: {str(e)}")

        return {
            "bucket": bucket,
            "key": key,
        }

    def copy_file(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> Dict:
        """
        Copy a file from one location to another within the storage

        Args:
            source_bucket: Source bucket name
            source_key: Source object key/path
            destination_bucket: Destination bucket name (use None for same as source)
            destination_key: Destination object key/path

        Returns:
            Dict with copy result information
        """
        source_bucket = source_bucket or self.default_bucket
        destination_bucket = destination_bucket or source_bucket

        try:
            # Construct copy source
            copy_source = {"Bucket": source_bucket, "Key": source_key}

            # Perform the copy operation
            response = self.internal_client.copy_object(
                CopySource=copy_source,
                Bucket=destination_bucket,
                Key=destination_key,
            )

            return {
                "source_bucket": source_bucket,
                "source_key": source_key,
                "destination_bucket": destination_bucket,
                "destination_key": destination_key,
                "etag": response.get("CopyObjectResult", {}).get("ETag", ""),
                "success": True,
            }

        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise Exception(
                    f"Source file {source_key} does not exist in bucket {source_bucket}"
                )
            raise Exception(
                f"Failed to copy file from {source_key} to {destination_key}: {str(e)}"
            )
        except Exception as e:
            raise Exception(
                f"Failed to copy file from {source_key} to {destination_key}: {str(e)}"
            )

    def generate_presigned_url(
        self, bucket: str, key: str, expires: int = 3600, method: str = "get_object"
    ) -> str:
        """
        Generate a presigned URL for S3/RustFS object

        Args:
            bucket: Bucket name
            key: Object key/path
            expires: URL expiration time in seconds
            method: HTTP method (get_object, put_object, delete_object)

        Returns:
            Presigned URL string
        """
        bucket = bucket or self.default_bucket

        operation_map = {
            "get_object": "get_object",
            "put_object": "put_object",
            "delete_object": "delete_object",
        }

        operation = operation_map.get(method, "get_object")

        try:
            url = self.external_client.generate_presigned_url(
                operation,
                Params={
                    "Bucket": bucket,
                    "Key": key,
                },
                ExpiresIn=expires,
                HttpMethod=(
                    "GET"
                    if operation == "get_object"
                    else "PUT" if operation == "put_object" else "DELETE"
                ),
            )
            return url
        except Exception as e:
            raise Exception(f"Failed to generate presigned URL for {key}: {str(e)}")

    def download_file(self, bucket: str, key: str, file_path: str) -> str:
        """Download a file from S3/RustFS to local path"""
        bucket = bucket or self.default_bucket

        try:
            self.internal_client.download_file(bucket, key, file_path)
            return file_path
        except Exception as e:
            raise Exception(
                f"Failed to download file {key} from bucket {bucket}: {str(e)}"
            )

    def delete_file(self, bucket: str, key: str) -> bool:
        """
        Delete a file from S3/RustFS

        Args:
            bucket: Bucket name
            key: Object key/path

        Returns:
            True if deleted successfully, False if file doesn't exist
        """
        bucket = bucket or self.default_bucket

        try:
            self.internal_client.delete_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return False
            raise Exception(
                f"Failed to delete file {key} from bucket {bucket}: {str(e)}"
            )
        except Exception as e:
            raise Exception(
                f"Failed to delete file {key} from bucket {bucket}: {str(e)}"
            )

    def move_file(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> Dict:
        """
        Move a file from one location to another (copy then delete)

        Args:
            source_bucket: Source bucket name
            source_key: Source object key/path
            destination_bucket: Destination bucket name
            destination_key: Destination object key/path

        Returns:
            Dict with move result information
        """
        # First copy the file
        copy_result = self.copy_file(
            source_bucket=source_bucket,
            source_key=source_key,
            destination_bucket=destination_bucket,
            destination_key=destination_key,
        )

        # Then delete the source
        self.delete_file(source_bucket, source_key)

        return {
            **copy_result,
            "moved": True,
        }


class AsyncStorageService:
    """Async wrapper for S3StorageService"""

    def __init__(self, sync_storage: Optional[S3StorageService] = None):
        if sync_storage is None:
            sync_storage = S3StorageService()
        self.storage = sync_storage

    async def ensure_bucket(self, bucket: str) -> None:
        """Async wrapper for ensure_bucket"""
        return await run_in_threadpool(self.storage.ensure_bucket, bucket)

    async def upload_file(
        self, bucket: str, key: str, file_obj: BinaryIO, content_type: str
    ) -> Dict:
        """Async wrapper for upload_file"""
        return await run_in_threadpool(
            self.storage.upload_file, bucket, key, file_obj, content_type
        )

    async def copy_file(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> Dict:
        """Async wrapper for copy_file"""
        return await run_in_threadpool(
            self.storage.copy_file,
            source_bucket,
            source_key,
            destination_bucket,
            destination_key,
        )

    async def move_file(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
    ) -> Dict:
        """Async wrapper for move_file (copy + delete)"""
        return await run_in_threadpool(
            self.storage.move_file,
            source_bucket,
            source_key,
            destination_bucket,
            destination_key,
        )

    async def generate_presigned_url(
        self, bucket: str, key: str, expires: int = 3600, method: str = "get_object"
    ) -> str:
        """Async wrapper for generate_presigned_url"""
        return await run_in_threadpool(
            self.storage.generate_presigned_url, bucket, key, expires, method
        )

    async def download_file(self, bucket: str, key: str, file_path: str) -> str:
        """Async wrapper for download_file"""
        return await run_in_threadpool(
            self.storage.download_file, bucket, key, file_path
        )

    async def delete_file(self, bucket: str, key: str) -> bool:
        """Async wrapper for delete_file"""
        return await run_in_threadpool(self.storage.delete_file, bucket, key)
