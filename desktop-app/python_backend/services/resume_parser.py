"""
Resume parser — extracts plain text from PDF and DOCX files.
"""

from pathlib import Path
import fitz  # PyMuPDF
import docx
import re


def _clean_text(text: str) -> str:
    """Normalise whitespace, remove null bytes, collapse blank lines."""
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_pdf(file_path: str) -> str:
    """Extract all text from a PDF file using PyMuPDF."""
    doc = fitz.open(file_path)
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return _clean_text("\n".join(pages))


def parse_docx(file_path: str) -> str:
    """Extract all text from a DOCX file using python-docx."""
    document = docx.Document(file_path)
    paragraphs = [para.text for para in document.paragraphs if para.text.strip()]
    return _clean_text("\n".join(paragraphs))


def parse_resume(file_path: str) -> str:
    """
    Dispatch to the correct parser based on file extension.

    Supported formats: .pdf, .docx
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Accepted: .pdf, .docx")
