"""Settings for the smoke scripts: the same variables and env file as scripts/env.sh."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

HOME = Path.home()


def _env_file() -> dict[str, str]:
    path = Path(os.environ.get("TEAMS_ENV", HOME / ".config/openshell-teams/env"))
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                out[key.strip()] = os.path.expandvars(value.strip().strip('"').strip("'").replace("$HOME", str(HOME)))
    return out


_FILE = _env_file()


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or _FILE.get(name) or default


REPO = Path(__file__).resolve().parent.parent
STATE = Path(setting("TEAMS_STATE", str(HOME / ".local/state/openshell-teams")))
OW_STATE = Path(setting("OW_STATE", str(STATE / "openworker")))
OPENWORKER_DIR = Path(setting("OPENWORKER_DIR", str(REPO.parent / "openworker")))
OPENSHELL = setting("OPENSHELL_BIN", shutil.which("openshell") or "openshell")
