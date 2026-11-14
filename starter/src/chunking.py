
"""Implement fixed-size and structure-aware chunking."""

from .models import Chunk, DocumentPage


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split a page into overlapping character windows."""
    if size <= 0:
        raise ValueError("size must be greater than 0")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and smaller than size")

    text = page.text.strip()
    if not text:
        return []

    chunks = []
    step = size - overlap

    for index, start in enumerate(range(0, len(text), step)):
        chunk_text = text[start : start + size].strip()

        if not chunk_text:
            continue

        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}_p{page.page}_fixed_{index}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=dict(page.metadata),
            )
        )

    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group paragraphs into chunks and split oversized paragraphs."""
    if max_size <= 0:
        raise ValueError("max_size must be greater than 0")

    text = page.text.strip()
    if not text:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in text.split("\n\n")
        if paragraph.strip()
    ]

    chunks = []
    current_parts = []
    current_length = 0

    def add_chunk(chunk_text: str) -> None:
        index = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=f"{page.document_id}_p{page.page}_paragraph_{index}",
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=chunk_text,
                metadata=dict(page.metadata),
            )
        )

    for paragraph in paragraphs:
        # Split a paragraph if it exceeds the maximum size.
        if len(paragraph) > max_size:
            if current_parts:
                add_chunk("\n\n".join(current_parts))
                current_parts = []
                current_length = 0

            for start in range(0, len(paragraph), max_size):
                piece = paragraph[start : start + max_size].strip()
                if piece:
                    add_chunk(piece)
            continue

        separator_length = 2 if current_parts else 0

        if current_length + separator_length + len(paragraph) > max_size:
            add_chunk("\n\n".join(current_parts))
            current_parts = [paragraph]
            current_length = len(paragraph)
        else:
            current_parts.append(paragraph)
            current_length += separator_length + len(paragraph)

    if current_parts:
        add_chunk("\n\n".join(current_parts))

    return chunks
