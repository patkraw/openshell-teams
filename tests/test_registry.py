import threading

import pytest

from openshell_teams.registry import Registry, LimitReached, RequestIdReused


@pytest.fixture
def reg(tmp_path):
    r = Registry(tmp_path / "registry.db")
    r.add_team("t1", max_workers=2)
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
    other = reg.reserve("t1", caller="lead-2", request_id="a", digest="d9", name="w2", role="worker", parent="lead-2")
    assert other["name"] == "w2" and other["retry"] is False


def test_stopping_a_parent_marks_it_stopping_and_lists_children_first(reg):
    reg.reserve("t1", caller="op", request_id="l", digest="dl", name="lead", role="lead", parent=None, counts=False)
    reg.reserve("t1", caller="lead", request_id="a", digest="d1", name="w1", role="worker", parent="lead")
    order = reg.begin_stop("lead")
    assert order == ["w1", "lead"]
    assert reg.get("lead")["state"] == "stopping"
    assert reg.is_stopping("lead")
