"""Where DocuSky credentials live on disk.

Resolution order:

1. ``DOCUSKY_USERNAME`` + ``DOCUSKY_PASSWORD`` environment variables.
2. A JSON file, by default ``~/.docusky/credentials.json``, overridable with
   ``DOCUSKY_CREDENTIALS``::

       {"username": "you@example.com", "password": "..."}

The file is written with mode 0600 and its directory with 0700.  In a packaged
``.mcpb`` install the environment variables are what the host fills in from the
extension's settings UI, so the file is only a fallback for other MCP clients.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path.home() / ".docusky" / "credentials.json"


def credentials_path() -> Path:
    override = os.environ.get("DOCUSKY_CREDENTIALS")
    return Path(override).expanduser() if override else DEFAULT_PATH


@dataclass
class Credentials:
    username: str | None = None
    password: str | None = None
    source: str = "none"  # "environment" | "file" | "none"
    path: Path | None = None
    warning: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.username and self.password)


def load_credentials() -> Credentials:
    env_user = os.environ.get("DOCUSKY_USERNAME")
    env_password = os.environ.get("DOCUSKY_PASSWORD")
    if env_user and env_password:
        return Credentials(env_user, env_password, source="environment")

    path = credentials_path()
    if not path.exists():
        return Credentials(source="none", path=path)

    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return Credentials(
            source="none", path=path, warning=f"Cannot read {path}: {exc}"
        )

    warning = None
    try:
        if path.stat().st_mode & 0o077:
            warning = (
                f"{path} is readable by other users; run "
                f"`chmod 600 {path}` to restrict it."
            )
    except OSError:
        pass

    return Credentials(
        username=raw.get("username"),
        password=raw.get("password"),
        source="file",
        path=path,
        warning=warning,
    )


def save_credentials(username: str, password: str, path: Path | None = None) -> Path:
    """Write credentials with private permissions, replacing any existing file."""
    target = path or credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    payload = json.dumps({"username": username, "password": password}, indent=2) + "\n"
    # os.open with 0600 so the secret is never briefly world-readable.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(payload)
    os.chmod(target, 0o600)
    return target


def delete_credentials(path: Path | None = None) -> bool:
    target = path or credentials_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
