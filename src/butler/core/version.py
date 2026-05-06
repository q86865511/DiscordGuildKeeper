"""App version + git sha discovery.

`APP_VERSION` mirrors the env var (which is also baked into image labels in CI).
`get_git_sha()` is best-effort — returns ``"unknown"`` when git is not available.
"""

from __future__ import annotations

import os
import subprocess

APP_VERSION: str = os.getenv("APP_VERSION", "0.1.0")


def get_git_sha() -> str:
    """Return a short git sha (12 chars), or ``"unknown"`` if unavailable.

    Order of resolution:
      1. ``GIT_SHA`` env var (CI / Docker may inject this at build time).
      2. ``git rev-parse`` if the binary is available and we are inside a repo.
      3. The literal string ``"unknown"``.
    """
    injected = os.getenv("GIT_SHA")
    if injected:
        return injected[:12]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return "unknown"
    return result.stdout.strip() or "unknown"
