from fastapi import APIRouter, UploadFile, File
from app.services.ocr_service import OCRService
from app.services.document_service import DocumentService

router = APIRouter(prefix="/uploads", tags=["multimodal"])


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    # Connect Tesseract in the next multimodal milestone.
    return {
        "filename": file.filename,
        "status": "received",
        "capability": "OCR",
    }


@router.post("/document")
async def upload_document(file: UploadFile = File(...)):
    # Connect PDF/DOCX extraction in the next document milestone.
    return {
        "filename": file.filename,
        "status": "received",
        "capability": "document-analysis",
    }
