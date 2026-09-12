"""The Space entrypoint, checked without deploying it.

Every assertion here corresponds to a deployment that failed. The file is not
imported by the application, so nothing else would notice if a line went
missing — and twice now an edit to it has silently removed one.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

ENTRYPOINT = pathlib.Path(__file__).parents[2] / "deploy" / "space" / "space_app.py"


@pytest.fixture(scope="module")
def source() -> str:
    return ENTRYPOINT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tree(source: str) -> ast.Module:
    return ast.parse(source)


def test_it_parses(tree: ast.Module) -> None:
    assert tree.body


def test_a_gpu_function_is_declared(tree: ast.Module) -> None:
    """Regression, twice over.

    ZeroGPU refuses to start a Space that declares no GPU work:
    `No @spaces.GPU function detected during startup`, and it is fatal. The
    declaration was lost once to an edit that replaced a span of the file and
    took the block with it, and the deployment is the only thing that noticed.
    """
    decorated = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        for decorator in node.decorator_list
        if "spaces" in ast.dump(decorator) and "GPU" in ast.dump(decorator)
    ]
    assert decorated, "no @spaces.GPU function — ZeroGPU will refuse to start"


def test_server_side_rendering_is_disabled(source: str) -> None:
    """Regression. SSR puts a Node proxy in front of Python on the public port.

    Only Gradio's own routes reach the Python app behind it, so everything this
    project mounts becomes unreachable while the Space looks healthy.
    """
    assert 'os.environ["GRADIO_SSR_MODE"] = "false"' in source


def test_the_api_is_mounted_not_included(source: str) -> None:
    """Regression. `include_router` appends a marker resolved at build time.

    Gradio has already built its route table by the time this runs, so the
    routes are added and never appear. A mount is resolved per request.
    """
    assert 'server.mount("/api"' in source
    assert "server.include_router" not in source


def test_the_entrypoint_is_not_named_app(source: str) -> None:
    """A module named `app` at the repository root shadows the app package."""
    assert ENTRYPOINT.name == "space_app.py"


def test_the_space_readme_points_at_this_file(source: str) -> None:
    readme = ENTRYPOINT.parents[1] / "space-readme.md"
    assert "app_file: space_app.py" in readme.read_text(encoding="utf-8")
