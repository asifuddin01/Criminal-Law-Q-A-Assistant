"""Documents uploaded by the user.

An uploaded document is not law. It may be a charge sheet, a notice, a draft, or a
photograph of a page from a textbook — and whatever it is, the system has no way to
establish its authority. Text from it is therefore carried under its own document
role and labelled as the user's document wherever it appears, so it can never be
presented with the standing of a statute.

Everything else about it is ordinary: it is chunked, retrieved and quoted like any
other source, and a quotation attributed to it is verified against it exactly as a
statutory quotation is verified against the Code.

Documents live in memory with a bounded capacity and are lost on restart. That is the
right lifetime for something a user uploaded to ask one question about, and it avoids
retaining people's legal papers on disk without being asked.
"""

from __future__ import annotations

import hashlib
import io
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from app.retrieval.chunking import Chunk

UPLOADED = "Uploaded"

# Generous for a charge sheet or a judgment, far below anything that would make
# extraction slow enough to block a request.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_PAGES = 120
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

PDF_MAGIC = b"%PDF-"


class UnreadableDocument(ValueError):
    """The upload could not be read as a document."""


@dataclass(slots=True)
class UploadedDocument:
    document_id: str
    filename: str
    media_type: str
    pages: int
    text: str
    uploaded_at: float = field(default_factory=time.time)

    @property
    def characters(self) -> int:
        return len(self.text)

    def preview(self, limit: int = 400) -> str:
        return " ".join(self.text.split())[:limit]

    def chunks(self) -> list[Chunk]:
        """Fixed windows over the document.

        Deliberately not the legal-aware strategy: that one splits on statutory
        section boundaries, and an arbitrary uploaded document has none. Pretending
        otherwise would attach section numbers to text that has no sections.
        """
        body = self.text
        step = max(1, CHUNK_CHARS - CHUNK_OVERLAP)
        out: list[Chunk] = []
        for index, start in enumerate(range(0, len(body), step)):
            window = body[start : start + CHUNK_CHARS]
            if not window.strip():
                continue
            out.append(
                Chunk(
                    chunk_id=f"upload-{self.document_id}-{index:04d}",
                    text=window,
                    section_number=f"p{index + 1}",
                    marginal_note=self.filename,
                    part=None,
                    chapter=None,
                    strategy="uploaded_document",
                    document=UPLOADED,
                )
            )
        return out


def extract(payload: bytes, *, filename: str, media_type: str) -> tuple[str, int]:
    """Pull text out of an upload, returning the text and a page count."""
    if not payload:
        raise UnreadableDocument("the uploaded file was empty")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise UnreadableDocument(
            f"file is {len(payload) / 1_048_576:.1f} MB; the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB"
        )

    if payload.startswith(PDF_MAGIC):
        return _extract_pdf(payload)

    if media_type.startswith("text/") or filename.lower().endswith((".txt", ".md")):
        try:
            return payload.decode("utf-8"), 1
        except UnicodeDecodeError as exc:
            raise UnreadableDocument("the file is not valid UTF-8 text") from exc

    raise UnreadableDocument(
        "only PDF and plain text are accepted. A scanned PDF with no text layer "
        "cannot be read either — this extracts text, it does not perform OCR."
    )


def _extract_pdf(payload: bytes) -> tuple[str, int]:
    import pdfplumber

    try:
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            pages = pdf.pages[:MAX_PAGES]
            text = "\n\n".join((page.extract_text() or "") for page in pages)
            count = len(pdf.pages)
    except Exception as exc:  # pdfplumber raises a variety of parser errors
        raise UnreadableDocument(f"the PDF could not be read: {exc}") from exc

    if not text.strip():
        raise UnreadableDocument(
            "no text could be extracted. The PDF is probably a scan, and this "
            "reads embedded text rather than performing OCR."
        )
    return text, count


class DocumentStore:
    """Bounded, in-memory store of uploaded documents."""

    def __init__(self, capacity: int = 32) -> None:
        self.capacity = capacity
        self._documents: OrderedDict[str, UploadedDocument] = OrderedDict()

    def add(self, payload: bytes, *, filename: str, media_type: str) -> UploadedDocument:
        text, pages = extract(payload, filename=filename, media_type=media_type)
        document_id = hashlib.sha256(payload).hexdigest()[:16]
        document = UploadedDocument(
            document_id=document_id,
            filename=filename or "document",
            media_type=media_type or "application/octet-stream",
            pages=pages,
            text=text,
        )
        self._documents[document_id] = document
        self._documents.move_to_end(document_id)
        while len(self._documents) > self.capacity:
            self._documents.popitem(last=False)
        return document

    def get(self, document_id: str) -> UploadedDocument | None:
        document = self._documents.get(document_id)
        if document is not None:
            self._documents.move_to_end(document_id)
        return document

    def __len__(self) -> int:
        return len(self._documents)
