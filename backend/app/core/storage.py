import asyncio
from uuid import uuid4

import boto3
from botocore.config import Config

from app.core.settings import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
    )


async def ping_storage() -> bool:
    try:
        await asyncio.to_thread(_client().head_bucket, Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False


async def upload_public_object(content: bytes, content_type: str, filename: str) -> tuple[str, str]:
    safe_name = "".join(character for character in filename if character.isalnum() or character in ".-_ ").strip().replace(" ", "-")
    object_key = f"uploads/{uuid4().hex}-{safe_name or 'file'}"
    await asyncio.to_thread(
        _client().put_object,
        Bucket=settings.s3_bucket,
        Key=object_key,
        Body=content,
        ContentType=content_type,
    )
    return object_key, f"{settings.s3_public_base_url.rstrip('/')}/{object_key}"


async def delete_object(object_key: str) -> None:
    await asyncio.to_thread(_client().delete_object, Bucket=settings.s3_bucket, Key=object_key)
