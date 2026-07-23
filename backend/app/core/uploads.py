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


DOCUMENT_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_document(file: UploadFile) -> tuple[str, int]:
    """Validate and store a document in the private documents dir.

    Returns (stored_name, size_bytes). 400 on an unsupported type. The file is
    never placed under the public /uploads mount.
    """
    extension = DOCUMENT_EXTENSIONS.get(file.content_type or "")
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported document type")
    data = await file.read()
    name = f"{uuid.uuid4().hex}{extension}"
    directory = Path(settings.documents_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(data)
    return name, len(data)


def delete_document_file(stored_name: str) -> None:
    """Remove a stored document file. A missing file is not an error."""
    Path(settings.documents_dir, stored_name).unlink(missing_ok=True)
