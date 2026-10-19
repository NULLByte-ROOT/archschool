from fastapi import APIRouter, Depends, File, UploadFile

from .. import models, schemas
from ..dependencies import get_current_user
from ..storage import save_upload

router = APIRouter()


@router.post("/", response_model=schemas.UploadOut)
async def upload_file(
    file: UploadFile = File(...),
    _: models.User = Depends(get_current_user),
):
    url, file_name, size = await save_upload(file)
    return schemas.UploadOut(url=url, file_name=file_name, size=size)
