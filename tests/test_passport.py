import time

import pytest

from openshell_teams import passport


@pytest.fixture
def keys(tmp_path):
    return passport.load_or_create_keys(tmp_path / "keys")


def test_signed_passport_verifies_and_names_the_sandbox(keys):
    token = passport.sign(keys.private, sandbox_id="sb-1", sandbox="reviewer", audience="board.local")
    claims = passport.verify(token, keys.public, audience="board.local")
    assert claims["sbx"] == "sb-1"
    assert claims["name"] == "reviewer"


def test_tampered_passport_is_rejected(keys):
    token = passport.sign(keys.private, sandbox_id="sb-1", sandbox="reviewer", audience="board.local")
    head, body, sig = token.split(".")
    forged = ".".join([head, body[:-2] + ("AA" if body[-2:] != "AA" else "BB"), sig])
    with pytest.raises(passport.InvalidPassport):
        passport.verify(forged, keys.public, audience="board.local")


def test_passport_for_another_service_is_rejected(keys):
    token = passport.sign(keys.private, sandbox_id="sb-1", sandbox="reviewer", audience="other.local")
    with pytest.raises(passport.InvalidPassport):
        passport.verify(token, keys.public, audience="board.local")


def test_expired_passport_is_rejected(keys):
    token = passport.sign(keys.private, sandbox_id="sb-1", sandbox="reviewer", audience="board.local",
                          now=time.time() - 3600)
    with pytest.raises(passport.InvalidPassport):
        passport.verify(token, keys.public, audience="board.local")


def test_passport_signed_by_another_key_is_rejected(keys, tmp_path):
    other = passport.load_or_create_keys(tmp_path / "other")
    token = passport.sign(other.private, sandbox_id="sb-1", sandbox="reviewer", audience="board.local")
    with pytest.raises(passport.InvalidPassport):
        passport.verify(token, keys.public, audience="board.local")


def test_keys_are_reused_once_created(tmp_path):
    first = passport.load_or_create_keys(tmp_path / "keys")
    second = passport.load_or_create_keys(tmp_path / "keys")
    assert first.public_pem == second.public_pem
