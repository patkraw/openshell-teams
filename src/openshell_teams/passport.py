"""Sandbox Passport: a short-lived signed caller identity naming the calling sandbox.

The Passport middleware signs one per request, outside the agent; services verify it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HEADER = "X-OpenShell-Caller"
ISSUER = "openshell-teams/passport"
LIFETIME_SECONDS = 60


class InvalidPassport(Exception):
    pass


@dataclass(frozen=True)
class Keys:
    private: Ed25519PrivateKey
    public_pem: bytes

    @property
    def public(self):
        return serialization.load_pem_public_key(self.public_pem)


def load_or_create_keys(directory: Path) -> Keys:
    directory = Path(directory)
    private_path = directory / "passport.key"
    public_path = directory / "passport.pub"
    if private_path.exists():
        private = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
        return Keys(private, public_path.read_bytes())
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    private = Ed25519PrivateKey.generate()
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    private_path.chmod(0o600)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    public_path.write_bytes(public_pem)
    return Keys(private, public_pem)


def sign(private_key, *, sandbox_id: str, sandbox: str, audience: str, now: float | None = None) -> str:
    issued = int(now if now is not None else time.time())
    claims = {"iss": ISSUER, "aud": audience, "sbx": sandbox_id, "name": sandbox,
              "iat": issued, "exp": issued + LIFETIME_SECONDS}
    return jwt.encode(claims, private_key, algorithm="EdDSA")


def verify(token: str, public_key, *, audience: str) -> dict:
    try:
        return jwt.decode(token, public_key, algorithms=["EdDSA"], audience=audience, issuer=ISSUER,
                          options={"require": ["exp", "iat", "aud", "iss", "sbx"]})
    except jwt.PyJWTError as error:
        raise InvalidPassport(str(error)) from error
