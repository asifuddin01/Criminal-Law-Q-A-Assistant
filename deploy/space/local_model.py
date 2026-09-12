"""Install and run Ollama inside a Hugging Face Space.

A Space is a single Python process with no persistent storage, so a local model
has to be fetched and started at runtime, every cold start. The cost is real and
worth stating before the code: Ollama's linux/amd64 bundle is **1.4 GB** and
`qwen2.5:3b-instruct` is another **1.9 GB**, so roughly **3.3 GB** is downloaded
each time the container starts, and inference then runs on the two shared vCPUs
a free Space gets.

It is therefore built to be entirely optional and entirely non-blocking:

  - the download and the server start on a background thread, so Gradio serves
    immediately and the hosted model answers while this is still arriving;
  - every failure is recorded as a status string and never raised, because a
    Space that will not start is worse than one without a second model;
  - progress is visible, so "it is still downloading" can be told apart from
    "it broke".

Set `ENABLE_LOCAL_MODEL=0` in the Space's variables to skip it entirely.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import threading
import time
import urllib.request

RELEASES = "https://api.github.com/repos/ollama/ollama/releases/latest"
ASSET = "ollama-linux-amd64.tar.zst"
DEFAULT_MODEL = "qwen2.5:3b-instruct"


class LocalModel:
    """An Ollama server fetched and run inside this process's container."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        home: pathlib.Path | None = None,
        host: str = "127.0.0.1:11434",
    ) -> None:
        self.model = model
        self.host = host
        self.home = home or pathlib.Path(os.environ.get("HOME", "/tmp")) / ".ollama-run"
        self._status = "not started"
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # -- observation ------------------------------------------------------

    @property
    def status(self) -> str:
        with self._lock:
            return self._status

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def _set(self, status: str) -> None:
        with self._lock:
            self._status = status
        print(f"local model: {status}", flush=True)

    # -- the work ---------------------------------------------------------

    def start_in_background(self) -> threading.Thread:
        """Fetch, start and pull, without blocking the caller."""
        thread = threading.Thread(target=self._run, name="local-model", daemon=True)
        thread.start()
        return thread

    def _run(self) -> None:
        try:
            binary = self._install()
            self._serve(binary)
            self._pull(binary)
            self._set("ready")
        except Exception as exc:  # noqa: BLE001 — a status, never a crash
            self._set(f"unavailable: {exc}")

    def _install(self) -> pathlib.Path:
        binary = self.home / "bin" / "ollama"
        if binary.exists():
            self._set("already installed")
            return binary

        url = self._asset_url()
        self.home.mkdir(parents=True, exist_ok=True)
        archive = self.home / ASSET

        self._set("downloading the ollama runtime (1.4 GB)")
        with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            seen = last = 0
            while chunk := response.read(1 << 20):
                out.write(chunk)
                seen += len(chunk)
                if total and seen - last > (1 << 28):  # every ~256 MB
                    last = seen
                    self._set(f"downloading the ollama runtime — {seen * 100 // total}%")

        self._set("extracting the ollama runtime")
        # tar handles zstd through the `zstd` package, which packages.txt installs.
        subprocess.run(
            ["tar", "--use-compress-program=unzstd", "-xf", str(archive), "-C", str(self.home)],
            check=True,
            capture_output=True,
        )
        archive.unlink(missing_ok=True)

        if not binary.exists():
            raise RuntimeError(f"no ollama binary at {binary} after extraction")
        binary.chmod(0o755)
        return binary

    def _asset_url(self) -> str:
        import json

        with urllib.request.urlopen(RELEASES, timeout=30) as response:
            release = json.load(response)
        for asset in release.get("assets", []):
            if asset.get("name") == ASSET:
                return asset["browser_download_url"]
        raise RuntimeError(f"{ASSET} is not in the latest ollama release")

    def _environment(self) -> dict[str, str]:
        env = dict(os.environ)
        env["OLLAMA_HOST"] = self.host
        env["OLLAMA_MODELS"] = str(self.home / "models")
        env["LD_LIBRARY_PATH"] = (
            f"{self.home / 'lib' / 'ollama'}:{env.get('LD_LIBRARY_PATH', '')}"
        )
        return env

    def _serve(self, binary: pathlib.Path) -> None:
        self._set("starting the ollama server")
        self._process = subprocess.Popen(
            [str(binary), "serve"],
            env=self._environment(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            if self._reachable():
                return
            if self._process.poll() is not None:
                raise RuntimeError(
                    f"the ollama server exited with code {self._process.returncode}"
                )
            time.sleep(1)
        raise RuntimeError("the ollama server did not become reachable in 60s")

    def _reachable(self) -> bool:
        try:
            with urllib.request.urlopen(f"http://{self.host}/api/tags", timeout=3):
                return True
        except Exception:  # noqa: BLE001
            return False

    def _pull(self, binary: pathlib.Path) -> None:
        self._set(f"pulling {self.model} (1.9 GB)")
        result = subprocess.run(
            [str(binary), "pull", self.model],
            env=self._environment(),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pulling {self.model} failed: {(result.stderr or '').strip()[:200]}"
            )
