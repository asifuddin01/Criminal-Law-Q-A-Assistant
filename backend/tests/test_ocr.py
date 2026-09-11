"""Image input via OCR.

The provider catalogue offers no vision model, so images are read with tesseract.
For a photograph of legal paper that is the better primitive anyway: the wanted
output is the text exactly as written, and a vision model would paraphrase it.

The live tests skip when tesseract is absent, since the endpoint is meant to degrade
rather than fail in that case, and that degradation is itself tested.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api import routes
from app.main import create_app
from app.qa import ocr

needs_tesseract = pytest.mark.skipif(
    not ocr.available(), reason="tesseract is not installed"
)


@pytest.fixture
def client():
    return TestClient(create_app())


def _post(client, content=b"fake image", content_type="image/png"):
    return client.post(
        "/api/image", files={"image": ("page.png", content, content_type)}
    )


# --- module ------------------------------------------------------------------------


def test_absence_of_the_binary_is_reported_not_raised(monkeypatch):
    """Missing OCR is a deployment fact, not a crash: the endpoint should say the
    feature is unavailable and name the fix."""
    monkeypatch.setattr(ocr, "binary", lambda: None)

    assert ocr.available() is False
    with pytest.raises(ocr.OCRUnavailable, match="brew install tesseract"):
        ocr.read_image(b"data")


def test_empty_and_oversized_images_are_refused(monkeypatch):
    monkeypatch.setattr(ocr, "binary", lambda: "/usr/bin/tesseract")

    with pytest.raises(ocr.UnreadableImage, match="empty"):
        ocr.read_image(b"")
    with pytest.raises(ocr.UnreadableImage, match="limit"):
        ocr.read_image(b"x" * (ocr.MAX_IMAGE_BYTES + 1))


def test_languages_are_limited_to_those_installed(monkeypatch):
    """Asking tesseract for a language it does not have fails the whole call, so the
    request is narrowed to what is actually present."""
    monkeypatch.setattr(ocr, "installed_languages", lambda: ("eng",))
    assert ocr.language_argument() == "eng"

    monkeypatch.setattr(ocr, "installed_languages", lambda: ("eng", "ben", "fra"))
    assert ocr.language_argument() == "eng+ben"

    monkeypatch.setattr(ocr, "installed_languages", lambda: ())
    assert ocr.language_argument() == "eng"


# --- endpoint ----------------------------------------------------------------------


def test_the_endpoint_says_so_when_ocr_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(ocr, "available", lambda: False)
    def unavailable(*args, **kwargs):
        raise ocr.OCRUnavailable("tesseract is not installed; install it")

    monkeypatch.setattr(routes.ocr, "read_image", unavailable)

    response = _post(client)

    assert response.status_code == 503
    assert "tesseract" in response.json()["detail"]


def test_the_endpoint_returns_text_for_the_user_to_check(client, monkeypatch):
    monkeypatch.setattr(routes.ocr, "read_image", lambda *a, **k: "FIRST INFORMATION REPORT")
    monkeypatch.setattr(routes.ocr, "language_argument", lambda: "eng+ben")

    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "FIRST INFORMATION REPORT"
    assert body["languages"] == "eng+ben"


def test_an_image_with_no_text_is_reported_rather_than_returned_empty(
    client, monkeypatch
):
    def no_text(*args, **kwargs):
        raise ocr.UnreadableImage("no text was found in the image")

    monkeypatch.setattr(routes.ocr, "read_image", no_text)

    response = _post(client)

    assert response.status_code == 422
    assert "no text" in response.json()["detail"]


def test_meta_lists_only_the_inputs_this_deployment_can_serve(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(routes.ocr, "available", lambda: False)

    features = client.get("/api/meta").json()["features"]

    # The local model has no Whisper and OCR is absent: neither is offered.
    assert "text" in features and "upload" in features
    assert "speech" not in features
    assert "image" not in features


def test_meta_offers_image_when_ocr_is_present(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setattr(routes.ocr, "available", lambda: True)

    assert "image" in client.get("/api/meta").json()["features"]


# --- live ---------------------------------------------------------------------------


@needs_tesseract
def test_bengali_language_data_is_available():
    """The corpus is English, but the paper a Bangladeshi user photographs often is
    not."""
    assert "ben" in ocr.installed_languages()


@needs_tesseract
def test_text_is_read_from_a_real_image():
    import io

    from PIL import Image, ImageDraw  # type: ignore[import-not-found]

    image = Image.new("RGB", (900, 160), "white")
    ImageDraw.Draw(image).text((20, 60), "SECTION 54 ARREST WITHOUT WARRANT", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    text = ocr.read_image(buffer.getvalue())

    assert "SECTION" in text.upper()
