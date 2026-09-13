"""
Extract plain text from an uploaded CV file (.pdf or .docx) so it can be
stored on the Profile and fed to the LLM for scoring/tailoring.
"""
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


def extract_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if suffix == ".docx":
        doc = DocxDocument(str(file_path))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts)

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8", errors="ignore")

    raise ValueError(f"Unsupported CV file type: {suffix}. Use .pdf, .docx or .txt")
