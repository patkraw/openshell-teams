"""The CLI wrapper must not report success it did not see (review findings 9, 18)."""

import pytest

from openshell_teams.openshell import OpenShellCLI, OpenShellError


def fake_cli(tmp_path, body: str):
    path = tmp_path / "openshell"
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)
    return OpenShellCLI(str(path), tmp_path / "logs")


def test_start_fails_when_the_agent_process_exits_at_once(tmp_path):
    cli = fake_cli(tmp_path, 'echo "no such persona" >&2; exit 3')
    with pytest.raises(OpenShellError) as e:
        cli.start("w", ["openworker", "agent"], grace_seconds=1)
    assert "no such persona" in str(e.value)


def test_start_succeeds_when_the_agent_keeps_running(tmp_path):
    cli = fake_cli(tmp_path, "sleep 5")
    cli.start("w", ["openworker", "agent"], grace_seconds=1)


def test_delete_failure_is_raised(tmp_path):
    cli = fake_cli(tmp_path, 'echo "gateway unavailable" >&2; exit 1')
    with pytest.raises(OpenShellError):
        cli.delete("w")


def test_delete_waits_for_the_sandbox_to_be_gone(tmp_path):
    # delete succeeds, then get reports "not found"
    cli = fake_cli(tmp_path, 'if [ "$2" = "get" ]; then echo "sandbox not found" >&2; exit 1; fi; exit 0')
    cli.delete("w")
