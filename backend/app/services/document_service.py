class DocumentService:
    """PDF/DOCX extraction extension point."""

    def extract_text(self, file_path: str) -> str:
        return ""
