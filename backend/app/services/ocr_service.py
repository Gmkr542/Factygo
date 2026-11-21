class OCRService:
    def extract_text(self, image_path: str) -> str:
        try:
            from PIL import Image
            import pytesseract
            return pytesseract.image_to_string(Image.open(image_path)).strip()
        except Exception:
            return ""
