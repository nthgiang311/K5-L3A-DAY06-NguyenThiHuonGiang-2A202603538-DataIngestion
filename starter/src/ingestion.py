"""Read and normalize source data."""
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace while preserving paragraph breaks."""
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t\f\v]+", " ", line)
        lines.append(line.strip())

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_pdf(path: Path, document_id: str, source: str) -> list[DocumentPage]:
    """Extract every physical PDF page and preserve its page number."""
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    reader = PdfReader(str(path))
    pages = []

    for page_number, pdf_page in enumerate(reader.pages, start=1):
        raw_text = pdf_page.extract_text() or ""
        normalized = normalize_text(raw_text)

        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=page_number,
                text=normalized,
                metadata={
                    "has_text": bool(normalized),
                    "character_count": len(normalized),
                    "page_type": "text" if normalized else "no_text",
                },
            )
        )

    return pages
