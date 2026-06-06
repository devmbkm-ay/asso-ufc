import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.deps import CurrentMember, RequireSecretary

UPLOAD_DIR = Path("/app/uploads")
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024  # 5 Mo

router = APIRouter(prefix="/upload", tags=["Upload"])


class UploadResponse(BaseModel):
    url: str


@router.post(
    "/image",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Uploader une image",
)
async def upload_image(
    current_member: CurrentMember,
    file: UploadFile = File(...),
    _=RequireSecretary,
):
    """Rôles requis : super_admin, secretary. Formats acceptés : JPEG, PNG, WEBP, GIF. Max 5 Mo."""
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Format non supporté. Utilisez JPEG, PNG, WEBP ou GIF.",
        )

    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fichier trop volumineux (maximum 5 Mo).",
        )

    ext = "jpg"
    if file.filename and "." in file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower()

    filename = f"{uuid.uuid4().hex}.{ext}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / filename).write_bytes(data)

    return UploadResponse(url=f"{settings.API_BASE_URL}/uploads/{filename}")
