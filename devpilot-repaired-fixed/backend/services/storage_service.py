"""Safe local/S3 storage adapter for DevPilot.

AWS credentials are resolved by boto3's standard provider chain:
environment, shared credentials/config, container/task role, or instance role.
Never place credentials in frontend code or commit them to source control.
"""
from __future__ import annotations

import mimetypes
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class StorageError(RuntimeError):
    """Raised when a storage operation cannot be completed."""


class StorageService:
    def __init__(self) -> None:
        self.mode = os.getenv("STORAGE_MODE", "local").strip().lower()
        if self.mode not in {"local", "s3"}:
            raise StorageError("STORAGE_MODE must be either 'local' or 's3'.")

        self.root = Path(os.getenv("LOCAL_STORAGE_PATH", "./storage")).expanduser().resolve()
        self.bucket = os.getenv("S3_BUCKET_NAME", "").strip()
        self.region = os.getenv("AWS_REGION", "ap-south-1").strip() or "ap-south-1"
        self.s3 = None

        if self.mode == "local":
            self.root.mkdir(parents=True, exist_ok=True)
        else:
            if not self.bucket:
                raise StorageError("S3 mode requires S3_BUCKET_NAME in backend/.env.")
            # Do not construct credentials manually. boto3's credential chain supports
            # rotated env keys, AWS profiles, ECS task roles and EC2 instance roles.
            self.session = boto3.Session(region_name=self.region)
            self.s3 = self.session.client(
                "s3",
                config=Config(
                    retries={"max_attempts": 5, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=30,
                ),
            )

    @staticmethod
    def _key(key: str) -> str:
        value = str(key).replace("\\", "/").lstrip("/")
        parts = PurePosixPath(value).parts
        if (
            not value
            or "\\x00" in value
            or any(part in {"..", "."} for part in parts)
            or value.endswith("//")
        ):
            raise ValueError("Invalid storage key.")
        return value

    def _local_path(self, key: str) -> Path:
        candidate = (self.root / self._key(key)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Invalid storage path.")
        return candidate

    def health(self) -> dict[str, Any]:
        if self.mode == "local":
            self.root.mkdir(parents=True, exist_ok=True)
            return {
                "connected": True,
                "mode": "local",
                "detail": "Local filesystem is available.",
            }
        try:
            assert self.s3 is not None
            self.s3.head_bucket(Bucket=self.bucket)
            identity = self.session.client("sts").get_caller_identity()
            return {
                "connected": True,
                "mode": "s3",
                "bucket": self.bucket,
                "region": self.region,
                "account": identity.get("Account"),
                "credential_source": "boto3 default credential provider chain",
                "detail": "S3 bucket access verified.",
            }
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "AWSClientError")
            message = error.get("Message", str(exc))
            if code in {"InvalidAccessKeyId", "SignatureDoesNotMatch", "ExpiredToken"}:
                message = (
                    f"AWS credentials rejected ({code}). Check the active access key "
                    "in backend/.env or configure an IAM role/profile. Do not paste secrets into chat."
                )
            return {
                "connected": False,
                "mode": "s3",
                "bucket": self.bucket,
                "region": self.region,
                "error_code": code,
                "detail": message,
            }
        except BotoCoreError as exc:
            return {
                "connected": False,
                "mode": "s3",
                "bucket": self.bucket,
                "region": self.region,
                "detail": str(exc),
            }

    def list(self, prefix: str = "") -> list[dict[str, Any]]:
        prefix = str(prefix).strip("/")
        if prefix:
            prefix = self._key(prefix).rstrip("/") + "/"

        if self.mode == "s3":
            assert self.s3 is not None
            items: dict[str, dict[str, Any]] = {}
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self.bucket, Prefix=prefix, Delimiter="/"
            ):
                for folder in page.get("CommonPrefixes", []):
                    key = folder["Prefix"]
                    items[key] = {
                        "name": key.rstrip("/").split("/")[-1],
                        "key": key,
                        "size": 0,
                        "type": "folder",
                        "is_folder": True,
                        "modified": None,
                    }
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key == prefix and key.endswith("/"):
                        continue
                    items[key] = {
                        "name": key.rstrip("/").split("/")[-1],
                        "key": key,
                        "size": obj["Size"],
                        "type": mimetypes.guess_type(key)[0] or "application/octet-stream",
                        "is_folder": key.endswith("/"),
                        "modified": obj["LastModified"].isoformat(),
                    }
            return sorted(items.values(), key=lambda item: (not item["is_folder"], item["name"].lower()))

        base = self._local_path(prefix) if prefix else self.root
        if not base.exists():
            return []
        return [
            {
                "name": path.name,
                "key": path.relative_to(self.root).as_posix() + ("/" if path.is_dir() else ""),
                "size": 0 if path.is_dir() else path.stat().st_size,
                "type": "folder" if path.is_dir() else (mimetypes.guess_type(path.name)[0] or "application/octet-stream"),
                "is_folder": path.is_dir(),
                "modified": __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
            for path in sorted(base.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        ]

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> dict[str, Any]:
        key = self._key(key)
        content_type = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
        if self.mode == "s3":
            assert self.s3 is not None
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
        else:
            path = self._local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return {"key": key, "size": len(data), "type": content_type, "storage": self.mode}

    def get_bytes(self, key: str) -> bytes:
        key = self._key(key)
        if self.mode == "s3":
            assert self.s3 is not None
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return self._local_path(key).read_bytes()

    def delete(self, key: str) -> None:
        key = self._key(key)
        if self.mode == "s3":
            assert self.s3 is not None
            if key.endswith("/"):
                paginator = self.s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=self.bucket, Prefix=key):
                    objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
                    if objects:
                        self.s3.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})
            else:
                self.s3.delete_object(Bucket=self.bucket, Key=key)
        else:
            path = self._local_path(key.rstrip("/"))
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    def create_folder(self, key: str) -> str:
        key = self._key(key).rstrip("/") + "/"
        if self.mode == "s3":
            assert self.s3 is not None
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=b"", ServerSideEncryption="AES256")
        else:
            self._local_path(key).mkdir(parents=True, exist_ok=True)
        return key

    def rename(self, old_key: str, new_key: str) -> str:
        old_key = self._key(old_key)
        new_key = self._key(new_key)
        if self.mode == "s3":
            assert self.s3 is not None
            if old_key.endswith("/"):
                raise ValueError("Folder rename is not supported by this endpoint; move individual objects instead.")
            self.s3.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": old_key},
                Key=new_key,
                ServerSideEncryption="AES256",
            )
            self.s3.delete_object(Bucket=self.bucket, Key=old_key)
        else:
            source = self._local_path(old_key)
            destination = self._local_path(new_key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
        return new_key


storage = StorageService()
