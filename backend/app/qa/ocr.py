"""Reading text out of an image.

The provider catalogue available to this project offers no vision model, so image
input is served by OCR rather than by a multimodal model.

That is not purely a workaround. The images this system expects are photographs of
legal paper — an FIR, a charge sheet, a notice, a page of a judgment — and for those
the wanted output is the text on the page, exactly as written. A vision model would
paraphrase; OCR transcribes. For a system whose claim is verbatim grounding, the
transcription is the better primitive.

Tesseract is invoked as a subprocess reading stdin and writing stdout, which avoids a
Python binding and keeps the failure mode legible: either the binary is there or the
endpoint says it is not.
"""

from __future__ import annotations

import functools
import shutil
import subprocess

# Bengali alongside English: the corpus is English but the paper a Bangladeshi user
# photographs frequently is not.
PREFERRED_LANGUAGES = ("eng", "ben")
TIMEOUT_SECONDS = 60
MAX_IMAGE_BYTES = 12 * 1024 * 1024

INSTALL_HINT = "install it with: brew install tesseract tesseract-lang"


class OCRUnavailable(RuntimeError):
    """Tesseract is not installed."""


class UnreadableImage(ValueError):
    """The image could not be read, or held no recognisable text."""


@functools.lru_cache(maxsize=1)
def binary() -> str | None:
    return shutil.which("tesseract")


@functools.lru_cache(maxsize=1)
def installed_languages() -> tuple[str, ...]:
    path = binary()
    if path is None:
        return ()
    try:
        result = subprocess.run(
            [path, "--list-langs"], capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    # The first line is a header; the rest are language codes.
    return tuple(line.strip() for line in result.stdout.splitlines()[1:] if line.strip())


def available() -> bool:
    return binary() is not None


def language_argument() -> str:
    """The languages to recognise, limited to those actually installed."""
    installed = installed_languages()
    wanted = [code for code in PREFERRED_LANGUAGES if code in installed]
    return "+".join(wanted) if wanted else "eng"


def read_image(payload: bytes, *, languages: str | None = None) -> str:
    """Extract text from an image."""
    path = binary()
    if path is None:
        raise OCRUnavailable(f"tesseract is not installed; {INSTALL_HINT}")
    if not payload:
        raise UnreadableImage("the uploaded image was empty")
    if len(payload) > MAX_IMAGE_BYTES:
        raise UnreadableImage(
            f"image is {len(payload) / 1_048_576:.1f} MB; the limit is "
            f"{MAX_IMAGE_BYTES // 1_048_576} MB"
        )

    try:
        result = subprocess.run(
            [path, "stdin", "stdout", "-l", languages or language_argument()],
            input=payload,
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise UnreadableImage("the image took too long to read") from exc
    except OSError as exc:
        raise OCRUnavailable(f"tesseract could not be run: {exc}") from exc

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise UnreadableImage(
            f"the image could not be read: {detail[-1] if detail else 'unknown error'}"
        )

    text = " ".join(result.stdout.decode("utf-8", "replace").split())
    if not text:
        raise UnreadableImage(
            "no text was found in the image. This reads text from a photograph of a "
            "document; it does not describe pictures."
        )
    return text
