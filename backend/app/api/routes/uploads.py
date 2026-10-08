from fastapi import APIRouter, UploadFile, File

router = APIRouter(prefix="/uploads", tags=["multimodal"])


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    # OCR integration will be added in the multimodal phase.
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "OCR pipeline",
    }


@router.post("/document")
async def upload_document(file: UploadFile = File(...)):
    # PDF/DOCX extraction will be added in the document phase.
    return {
        "filename": file.filename,
        "status": "received",
        "next_step": "document extraction pipeline",
    }
