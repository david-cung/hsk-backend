from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.config import settings


class MediaStorage(Protocol):
    provider: str

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        ...

    def get_download_url(self, key: str, expires_seconds: int) -> str:
        ...

    def get_upload_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        ...

    def delete(self, key: str) -> None:
        ...


class LocalMediaStorage:
    provider = "local"

    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root != path and self.root not in path.parents:
            raise ValueError("Invalid media key")
        return path

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get_download_url(self, key: str, expires_seconds: int) -> str:
        del expires_seconds
        return f"/api/v1/media/{key}"

    def get_upload_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        del key, content_type, expires_seconds
        raise RuntimeError("Local media uploads must use the application upload path")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3MediaStorage:
    provider = "s3"

    def __init__(self) -> None:
        import boto3

        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required for S3 media storage")
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def put_bytes(self, key: str, content: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=content_type)

    def get_download_url(self, key: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_seconds
        )

    def get_upload_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        return self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_seconds,
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_media_storage() -> MediaStorage:
    if settings.media_storage_provider.lower() == "s3":
        return S3MediaStorage()
    return LocalMediaStorage(settings.media_storage_dir)
