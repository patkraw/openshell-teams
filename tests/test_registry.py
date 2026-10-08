import threading

import pytest

from openshell_teams.registry import Registry, LimitReached, RequestIdReused


@pytest.fixture
def reg(tmp_path):
    r = Registry(tmp_path / "registry.db")
    r.add_team("t1", max_workers=2)
    # workers are reserved under a running lead
    r.reserve("t1", caller="op", request_id="lead", digest="dl", name="lead", role="lead", parent=None, counts=False)
    r.update("lead", state="running")
    return r


def test_slots_are_reserved_until_the_limit(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    reg.reserve("t1", caller="lead", request_id="b", digest="d2", name="w2", role="worker", parent="lead")
    with pytest.raises(LimitReached):
        reg.reserve("t1", caller="lead", request_id="c", digest="d3", name="w3", role="worker", parent="lead")


def test_concurrent_requests_cannot_both_take_the_last_slot(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    outcomes = []

    def take(i):
        try:
            reg.reserve("t1", caller="lead", request_id=f"x{i}", digest=f"dx{i}", name=f"x{i}", role="worker", parent="lead")
            outcomes.append("ok")
        except LimitReached:
            outcomes.append("full")

    threads = [threading.Thread(target=take, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert outcomes.count("ok") == 1


def test_retry_with_same_request_id_returns_the_same_agent(reg):
    first = reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    again = reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    assert again["name"] == first["name"] and again["retry"] is True


def test_reusing_a_request_id_for_a_different_request_is_an_error(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    with pytest.raises(RequestIdReused):
        reg.reserve("t1", caller="lead", request_id="a", digest="other", name="w2", role="worker", parent="lead")


def test_request_ids_are_scoped_to_the_caller(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    other = reg.reserve("t1", caller="lead-2", request_id="a", digest="d9", name="w2", role="worker", parent="lead")
    assert other["name"] == "w2" and other["retry"] is False


def test_stopping_a_parent_marks_it_stopping_and_lists_children_first(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    order = reg.begin_stop("lead")
    assert order == ["w1", "lead"]
    assert reg.get("lead")["state"] == "stopping"
    assert reg.is_stopping("lead")


def test_a_name_can_be_reused_after_the_agent_stopped_and_history_is_kept(reg):
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    reg.update("w1", state="stopped")
    again = reg.reserve("t1", caller="lead", request_id="b", digest="d2", name="w1", role="worker", parent="lead")
    assert again["retry"] is False and again["state"] == "reserved"
    assert [r["state"] for r in reg.history("w1")] == ["stopped", "reserved"]


def test_two_live_agents_cannot_share_a_name(reg):
    from openshell_teams.registry import NameInUse
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    with pytest.raises(NameInUse):
        reg.reserve("t1", caller="lead", request_id="b", digest="d2", name="w1", role="worker", parent="lead")


def test_reserving_under_a_parent_that_is_not_running_is_refused(reg):
    """Review finding 6: the parent's state was checked outside the reservation."""
    from openshell_teams.registry import ParentNotRunning
    reg.begin_stop("lead")
    with pytest.raises(ParentNotRunning):
        reg.reserve("t1", caller="sb", request_id="w", digest="d", name="w", role="worker", parent="lead")


def test_transitions_are_conditional(reg):
    reg.reserve("t1", caller="op", request_id="1", digest="d", name="a", role="worker", parent=None)
    assert reg.transition("a", ("reserved",), "creating")
    assert not reg.transition("a", ("reserved",), "creating")
    reg.begin_stop("a")
    assert not reg.transition("a", ("creating",), "created")
    assert reg.get("a")["state"] == "stopping"


def test_stop_reaches_children_that_are_still_being_created(reg):
    reg.reserve("t1", caller="sb", request_id="w", digest="d", name="w", role="worker", parent="lead")
    reg.transition("w", ("reserved",), "creating")
    assert reg.begin_stop("lead") == ["w", "lead"]


def test_a_rejected_admission_is_remembered_for_retries(reg):
    """Review finding 13: a retry returned the stopped record as if it had succeeded."""
    reg.reserve("t1", caller="sb", request_id="r1", digest="d", name="w", role="worker", parent=None)
    reg.reject("w", "approval_required", "needs approval")
    again = reg.reserve("t1", caller="sb", request_id="r1", digest="d", name="w", role="worker", parent=None)
    assert again["retry"] and again["error_code"] == "approval_required"
    # a rejected agent holds neither its name nor a slot
    reg.reserve("t1", caller="sb", request_id="r2", digest="e", name="w", role="worker", parent=None)
