class OCRService:
    """OCR extension point.

    Tesseract can be connected here without changing the API contract.
    """

    def extract_text(self, image_path: str) -> str:
        return ""
