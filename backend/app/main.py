"""Application entry point."""

from __future__ import annotations

import contextlib
import logging
import pathlib
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import get_settings
from app.services import warm

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the corpus and index once, before the first request.

    A missing index is reported rather than fatal: a deployment that has not been
    ingested should start and say what is wrong, not refuse to boot. /ask then
    answers 503 with the command that fixes it.
    """
    for component, state in warm().items():
        logger.info("%s: %s", component, state)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        description=(
            "Source-grounded question answering over Bangladesh criminal law. "
            "Provides legal information, not legal advice."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="/api")

    # The exported frontend, when one has been built into the image. Mounted last
    # so it never shadows /api, and absent in development, where Next serves
    # itself on another port.
    static = pathlib.Path(__file__).resolve().parents[1] / "static"
    if (static / "index.html").exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")
        logger.info("serving the exported frontend from %s", static)

    return app


app = create_app()
