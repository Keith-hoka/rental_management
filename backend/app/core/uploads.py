import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import settings

IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def delete_image_file(url: str) -> None:
    """Remove a stored upload. A missing file is not an error worth raising."""
    Path(settings.upload_dir, Path(url).name).unlink(missing_ok=True)


async def save_image(file: UploadFile) -> str:
    """Validate and store an uploaded image; return its /uploads URL."""
    extension = IMAGE_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported image type")
    name = f"{uuid.uuid4().hex}{extension}"
    directory = Path(settings.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(await file.read())
    return f"/uploads/{name}"
