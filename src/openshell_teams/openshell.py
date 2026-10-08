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
    def __init__(self, binary: str, log_dir: Path, image: str | None = None):
        self.bin = binary
        self.image = image   # sandbox image for every agent, e.g. openworker:local
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.processes: dict[str, subprocess.Popen] = {}   # running agent exec sessions

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
        if self.image:
            args += ["--from", self.image]
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

    def start(self, name: str, command: list[str], env: dict | None = None, grace_seconds: float = 8) -> None:
        """Start the agent and watch it for a short grace period: a command that exits at
        once (bad persona, missing binary, failed exec) is a failed start, not a running agent."""
        args = [self.bin, "sandbox", "exec", "-n", name, "--no-tty"]
        for k, v in (env or {}).items():
            args += ["--env", f"{k}={v}"]
        log_path = self.log_dir / f"{name}.log"
        offset = log_path.stat().st_size if log_path.exists() else 0
        with open(log_path, "ab") as log:
            proc = subprocess.Popen([*args, "--", *command], stdout=log, stderr=log, start_new_session=True)
        try:
            code = proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            self.processes[name] = proc
            return
        with open(log_path, "rb") as log:
            log.seek(offset)
            tail = log.read().decode(errors="replace").strip()[-400:]
        raise OpenShellError(f"agent {name} exited at start (code {code}): {tail}")

    def delete(self, name: str) -> None:
        """Delete and wait until the sandbox is gone, so its name can be reused. Raises if
        the delete fails or the sandbox is still there at the deadline; deleting a sandbox
        that does not exist succeeds."""
        proc = self.processes.pop(name, None)
        self._run("sandbox", "delete", name, timeout=120)
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                self.get(name)
            except OpenShellError as error:
                if "not found" in str(error):
                    if proc and proc.poll() is None:
                        proc.terminate()
                    return
                raise
            time.sleep(2)
        raise OpenShellError(f"sandbox {name} still present after delete")
