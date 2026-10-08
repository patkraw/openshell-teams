"""How Spawn Gate registers and removes agents on a board."""

from __future__ import annotations

import httpx

from .refboard import ADMIN_HEADER


class BoardRegistrar:
    def __init__(self, admin_url: str, admin_token: str):
        self.url = admin_url.rstrip("/")
        self.headers = {ADMIN_HEADER: admin_token}

    def register(self, sandbox_id: str, team: str, name: str, role: str) -> None:
        r = httpx.post(f"{self.url}/v1/admin/agents", headers=self.headers, timeout=10,
                       json={"sandbox_id": sandbox_id, "team": team, "name": name, "role": role})
        r.raise_for_status()

    def deregister(self, sandbox_id: str) -> None:
        r = httpx.delete(f"{self.url}/v1/admin/agents/{sandbox_id}", headers=self.headers, timeout=10)
        r.raise_for_status()


class ApprovalClient:
    """Consumes single-use approval IDs with the harness that showed the approval card."""

    def __init__(self, admin_url: str, admin_token: str):
        self.url = admin_url.rstrip("/")
        self.headers = {ADMIN_HEADER: admin_token}

    def consume(self, approval_id: str, *, team: str, lead: str, worker: str, digest: str) -> None:
        r = httpx.post(f"{self.url}/v1/admin/approvals/consume", headers=self.headers, timeout=10,
                       json={"approval_id": approval_id, "team": team, "lead": lead,
                             "worker": worker, "digest": digest})
        if r.status_code != 200:
            raise PermissionError(r.json().get("error", r.text))
