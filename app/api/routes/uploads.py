import os
import tempfile
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from app.services.document_service import DocumentService
from app.services.ocr_service import OCRService

router = APIRouter()


@router.post("/uploads")
async def upload_file(file: UploadFile = File(...)):
    suffix = Path(file.filename or "upload.txt").suffix.lower()
    content = await file.read(15 * 1024 * 1024 + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds 15MB limit.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            extracted = OCRService().extract_text(tmp_path)
        else:
            extracted = DocumentService().extract_text(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {
        "filename": file.filename,
        "extracted_text": extracted[:15000],
        "characters": len(extracted),
    }
