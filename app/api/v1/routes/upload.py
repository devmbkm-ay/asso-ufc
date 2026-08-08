from fastapi import APIRouter, File, UploadFile, status
from pydantic import BaseModel

from app.core.deps import CurrentMember, RequireSecretary
from app.core.uploads import save_uploaded_image

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
    return UploadResponse(url=await save_uploaded_image(file))
