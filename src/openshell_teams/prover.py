"""Run openshell-prover on two policies and return its verdict."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import yaml


class Prover:
    def __init__(self, binary: str, timeout_seconds: int = 20, keep_dir=None):
        self.binary = binary
        # When set, each check's inputs and output are kept here for inspection.
        self.keep_dir = Path(keep_dir) if keep_dir else None
        self.checks = 0
        self.timeout = timeout_seconds

    def check(self, candidate: dict, boundary: dict, label: str = "") -> tuple[str, str]:
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
        verdict = match.group(1) if match else "error"
        if self.keep_dir:
            self.checks += 1
            slug = re.sub(r"[^a-z0-9]+", "-", (label or "check").lower()).strip("-")
            base = self.keep_dir / f"{self.checks:04d}-{slug}"
            self.keep_dir.mkdir(parents=True, exist_ok=True)
            Path(f"{base}.candidate.yaml").write_text(yaml.safe_dump(candidate))
            Path(f"{base}.ceiling.yaml").write_text(yaml.safe_dump(boundary))
            Path(f"{base}.out.txt").write_text(out)
            self.last_saved = str(base)
        return verdict, out.strip()
