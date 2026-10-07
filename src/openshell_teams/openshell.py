"""Thin client over the OpenShell 0.1.2 CLI: create without starting, read the
effective policy back, start a command, delete."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

GENERATION = "internal.openshell.ai/runtime-generation"


class OpenShellError(RuntimeError):
    pass


class OpenShellCLI:
    def __init__(self, binary: str, log_dir: Path):
        self.bin = binary
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _run(self, *args, timeout=300) -> str:
        run = subprocess.run([self.bin, *args], capture_output=True, text=True, timeout=timeout)
        if run.returncode != 0:
            raise OpenShellError(f"openshell {' '.join(args[:3])}: {run.stderr.strip()[-400:]}")
        return run.stdout

    def get(self, name: str) -> dict:
        return json.loads(self._run("sandbox", "get", name, "-o", "json", timeout=60))

    def create(self, name: str, grant: dict, providers, labels) -> dict:
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            yaml.safe_dump(grant, f)
        args = ["sandbox", "create", "--name", name, "--detach", "--no-tty", "--no-auto-providers",
                "--policy", f.name]
        for p in providers:
            args += ["--provider", p]
        for k, v in labels.items():
            args += ["--label", f"{k}={v}"]
        self._run(*args)
        deadline = time.time() + 180
        while time.time() < deadline:
            sb = self.get(name)
            if sb.get("phase") == "Ready":
                return {"id": sb["id"], "generation": sb.get("annotations", {}).get(GENERATION)}
            if sb.get("phase") in ("Error", "Failed"):
                raise OpenShellError(f"sandbox {name} failed: {sb.get('phase')}")
            time.sleep(2)
        raise OpenShellError(f"sandbox {name} not ready in time")

    def effective_policy(self, name: str) -> dict:
        return yaml.safe_load(self._run("sandbox", "get", name, "--policy-only", timeout=60))

    def start(self, name: str, command: list[str], env: dict | None = None) -> None:
        args = [self.bin, "sandbox", "exec", "-n", name, "--no-tty"]
        for k, v in (env or {}).items():
            args += ["--env", f"{k}={v}"]
        log = open(self.log_dir / f"{name}.log", "ab")
        subprocess.Popen([*args, "--", *command], stdout=log, stderr=log, start_new_session=True)

    def delete(self, name: str) -> None:
        try:
            self._run("sandbox", "delete", name, timeout=120)
        except OpenShellError:
            pass
