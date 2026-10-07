"""Run openshell-prover on two policies and return its verdict."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import yaml


class Prover:
    def __init__(self, binary: str, timeout_seconds: int = 20):
        self.binary = binary
        self.timeout = timeout_seconds

    def check(self, candidate: dict, boundary: dict) -> tuple[str, str]:
        """Return (verdict, detail). Verdict is within_boundary, exceeds_boundary,
        unsupported, inconclusive or error."""
        with tempfile.TemporaryDirectory() as tmp:
            c, b = Path(tmp) / "candidate.yaml", Path(tmp) / "boundary.yaml"
            c.write_text(yaml.safe_dump(candidate))
            b.write_text(yaml.safe_dump(boundary))
            try:
                run = subprocess.run([self.binary, "check", str(c), "--boundary", str(b),
                                      "--timeout", f"{self.timeout}s"],
                                     capture_output=True, text=True, timeout=self.timeout + 10)
            except subprocess.TimeoutExpired:
                return "inconclusive", "prover did not finish in time"
        out = run.stdout + run.stderr
        match = re.search(r"result:\s*(\w+)", out)
        return (match.group(1) if match else "error"), out.strip()
