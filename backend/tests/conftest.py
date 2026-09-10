"""Test isolation.

Settings load from a `.env` in the working directory, so a developer with a
configured environment would otherwise get different test behaviour from one
without. That is not a hypothetical: the missing-key test passed only while no
`.env` existed, and silently stopped testing anything the moment one did.

Tests therefore run from a directory that has no `.env`, and the settings and
provider caches are cleared around every test so configuration set by one test
cannot leak into the next.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from app.config import get_settings
from app.llm.registry import get_provider


@pytest.fixture(scope="session", autouse=True)
def _isolate_from_developer_dotenv(tmp_path_factory):
    """Run the suite from a directory containing no .env file.

    Every path the application resolves is derived from __file__ rather than the
    working directory, so this is safe.
    """
    original = pathlib.Path.cwd()
    os.chdir(tmp_path_factory.mktemp("isolated-cwd"))
    try:
        yield
    finally:
        os.chdir(original)


@pytest.fixture(autouse=True)
def _reset_configuration_caches():
    get_settings.cache_clear()
    get_provider.cache_clear()
    yield
    get_settings.cache_clear()
    get_provider.cache_clear()
