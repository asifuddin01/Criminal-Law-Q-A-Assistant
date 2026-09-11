"""Uploaded documents.

An uploaded file is not law. These tests pin that distinction, because the failure
mode is a system that cites whatever a visitor uploaded with the standing of a
statute.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.qa.documents import (
    MAX_UPLOAD_BYTES,
    UPLOADED,
    DocumentStore,
    UnreadableDocument,
    extract,
)


@pytest.fixture
def store():
    return DocumentStore(capacity=3)


@pytest.fixture
def client():
    return TestClient(create_app())


def _pdf_bytes(text: str = "Charge sheet under section 379 of the Penal Code.") -> bytes:
    """A minimal real PDF, built with the library already in the project."""
    import io

    from reportlab.pdfgen import canvas  # type: ignore[import-not-found]

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()


# --- extraction --------------------------------------------------------------------


def test_plain_text_is_accepted():
    text, pages = extract(b"hello", filename="note.txt", media_type="text/plain")

    assert text == "hello"
    assert pages == 1


def test_an_empty_upload_is_refused():
    with pytest.raises(UnreadableDocument, match="empty"):
        extract(b"", filename="a.txt", media_type="text/plain")


def test_an_oversized_upload_is_refused():
    with pytest.raises(UnreadableDocument, match="limit"):
        extract(
            b"x" * (MAX_UPLOAD_BYTES + 1), filename="a.txt", media_type="text/plain"
        )


def test_an_unsupported_type_says_what_is_accepted():
    with pytest.raises(UnreadableDocument, match="PDF and plain text"):
        extract(b"\x89PNG\r\n", filename="scan.png", media_type="image/png")


def test_a_pdf_with_no_text_layer_is_refused_rather_than_accepted_empty():
    """A scan extracts to nothing. Accepting it would produce a document that
    answers every question with silence and no explanation."""
    blank = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"

    with pytest.raises(UnreadableDocument):
        extract(blank, filename="scan.pdf", media_type="application/pdf")


# --- store -------------------------------------------------------------------------


def test_the_same_file_uploaded_twice_keeps_one_id(store):
    first = store.add(b"same", filename="a.txt", media_type="text/plain")
    second = store.add(b"same", filename="a.txt", media_type="text/plain")

    assert first.document_id == second.document_id
    assert len(store) == 1


def test_the_store_is_bounded(store):
    for index in range(5):
        store.add(f"doc {index}".encode(), filename="a.txt", media_type="text/plain")

    assert len(store) == 3


def test_chunks_carry_the_uploaded_role_not_a_statutory_one(store):
    document = store.add(
        b"Some text about an arrest.", filename="fir.txt", media_type="text/plain"
    )

    chunks = document.chunks()

    assert chunks
    assert all(c.document == UPLOADED for c in chunks)
    assert all(c.strategy == "uploaded_document" for c in chunks)
    # Never a statutory section number: the document has no sections.
    assert all(c.section_number.startswith("p") for c in chunks)


def test_a_long_document_is_split_into_several_chunks(store):
    document = store.add(
        ("paragraph. " * 500).encode(), filename="long.txt", media_type="text/plain"
    )

    assert len(document.chunks()) > 1


# --- endpoint ----------------------------------------------------------------------


def test_uploading_returns_an_id_and_a_notice(client, monkeypatch):
    monkeypatch.setattr(routes, "_documents", DocumentStore())

    response = client.post(
        "/api/documents",
        files={"file": ("fir.txt", b"First Information Report", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_id"]
    assert body["pages"] == 1
    assert "not part of the legal corpus" in body["notice"]
    assert "First Information" in body["preview"]


def test_an_unreadable_upload_is_a_422_with_the_reason(client, monkeypatch):
    monkeypatch.setattr(routes, "_documents", DocumentStore())

    response = client.post(
        "/api/documents", files={"file": ("x.png", b"\x89PNG\r\n", "image/png")}
    )

    assert response.status_code == 422
    assert "PDF and plain text" in response.json()["detail"]


def test_asking_against_a_document_that_is_gone_explains_why(client, monkeypatch):
    """Uploads live in memory, so a restart loses them. Saying so beats a bare 404."""
    monkeypatch.setattr(routes, "_documents", DocumentStore())

    response = client.post(
        "/api/ask", json={"question": "What does this say?", "document_id": "missing"}
    )

    assert response.status_code == 404
    assert "restarts" in response.json()["detail"]
