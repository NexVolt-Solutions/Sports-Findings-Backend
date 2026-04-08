import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.config import settings


ALLOWED_AVATAR_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


async def save_avatar_upload(user_id: str, file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar file must have a filename",
        )

    if file.content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Avatar must be a JPEG, PNG, WEBP, or GIF image",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded avatar file is empty",
        )

    max_size_bytes = settings.max_avatar_size_mb * 1024 * 1024
    if len(content) > max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Avatar file exceeds {settings.max_avatar_size_mb} MB limit",
        )

    extension = Path(file.filename).suffix.lower() or ".bin"
    upload_root = Path(settings.uploads_dir)
    avatar_dir = upload_root / "avatars" / user_id
    avatar_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{extension}"
    destination = avatar_dir / filename
    destination.write_bytes(content)

    base_url = settings.app_base_url.rstrip("/")
    return f"{base_url}/uploads/avatars/{user_id}/{filename}"
