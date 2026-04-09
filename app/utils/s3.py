import uuid
from typing import Optional
import aioboto3
from fastapi import HTTPException, status, UploadFile
from app.config import settings


def _make_s3_object_key(user_id: str, original_filename: str) -> str:
    safe_filename = original_filename.replace(" ", "_")
    return f"avatars/{user_id}/{uuid.uuid4().hex}_{safe_filename}"


def _public_url_for_key(key: str) -> str:
    if settings.cloudfront_domain:
        return f"https://{settings.cloudfront_domain}/{key}"
    # Standard S3 public URL format using bucket policy for public access
    return f"https://{settings.aws_s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"


async def upload_avatar_to_s3(user_id: str, file: UploadFile) -> str:
    if not settings.aws_access_key_id or not settings.aws_secret_access_key or not settings.aws_s3_bucket_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AWS S3 credentials are not configured",
        )

    object_key = _make_s3_object_key(user_id, file.filename)

    session = aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )

    try:
        async with session.client("s3") as s3:
            content = await file.read()
            if not content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded avatar file is empty",
                )
            await s3.put_object(
                Bucket=settings.aws_s3_bucket_name,
                Key=object_key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
                # ACL removed — bucket uses bucket policy for public read access
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar to S3: {exc}",
        )

    return _public_url_for_key(object_key)

