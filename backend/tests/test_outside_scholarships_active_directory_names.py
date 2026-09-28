"""E2E: the "Active Directory Name" column is filled from Microsoft Graph by PID.

Runs the real route, extraction graph, Graph lookup and Excel writer. Document
Intelligence, the LLM and Graph are faked (see outside_scholarships_fakes.py). The
PID printed on each check's back is looked up as the Entra ID `employeeId`, using the
signed-in user's own token. The mixed-upload test saves its workbook as a reviewable
artifact under tests/artifacts/.
"""

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from outside_scholarships_fakes import (
    BACK,
    FIRST_DATA_ROW,
    FRONT,
    HEADER_ROW,
    FakeGraph,
    graph_user,
    upload,
)

_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "outside_scholarships_active_directory_names.xlsx"
_LOOKUP_FAILED = "Lookup failed"
_GRAPH_FILTER_MAX_VALUES = 15

_JANE_PID = "730000001"
_JANE = graph_user(_JANE_PID, given_name="Jane", surname="Doe", display_name="Jane Doe")


def _worksheet(response):
    return load_workbook(BytesIO(response.content)).active


def _pid_and_directory_name_rows(response):
    """(PID, Active Directory Name) for every data row, blanks as ""."""
    return [
        (pid or "", directory_name or "")
        for pid, _amount, _name, directory_name, *_ in _worksheet(response).iter_rows(
            min_row=FIRST_DATA_ROW, values_only=True
        )
    ]


def _all_requested_pids(graph):
    return [pid for request in graph.requests for pid in graph.requested_pids(request)]


def test_active_directory_name_column_follows_check_name(client, override_auth, app):
    response, _, _ = upload(client, app, [FRONT])

    assert response.status_code == 200, response.text
    assert [cell.value for cell in _worksheet(response)[HEADER_ROW]] == [
        "PID",
        "Amount",
        "Name",
        "Active Directory Name",
        "Aid year",
        "Aid term",
        "Provider",
        "Scholarship name",
    ]


def test_pid_found_in_directory_gets_last_first_name(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _, _ = upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane")]


def test_pid_missing_from_directory_is_blank(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _, _ = upload(client, app, [FRONT, BACK], back_pids={1001: "730009999"}, graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [("730009999", "")]


def test_check_without_pid_is_blank_and_not_looked_up(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _, _ = upload(client, app, [FRONT, BACK, FRONT], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane"), ("", "")]
    assert _all_requested_pids(graph) == [_JANE_PID]


def test_upload_without_pids_makes_no_graph_request(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _, _ = upload(client, app, [FRONT, FRONT], graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [("", ""), ("", "")]
    assert graph.requests == []


def test_repeated_pid_is_looked_up_once_and_filled_on_every_row(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _, _ = upload(
        client, app, [FRONT, BACK, FRONT, BACK], back_pids={1001: _JANE_PID, 1002: _JANE_PID}, graph=graph
    )

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane"), (_JANE_PID, "Doe, Jane")]
    assert _all_requested_pids(graph) == [_JANE_PID]


def test_more_than_fifteen_pids_are_split_across_requests(client, override_auth, app):
    check_count = _GRAPH_FILTER_MAX_VALUES + 1
    pids = {1000 + index: f"7300000{index:02d}" for index in range(1, check_count + 1)}
    graph = FakeGraph(
        {pid: graph_user(pid, given_name=f"Given{pid[-2:]}", surname=f"Surname{pid[-2:]}") for pid in pids.values()}
    )

    response, _, _ = upload(client, app, [FRONT, BACK] * check_count, back_pids=pids, graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [
        (pid, f"Surname{pid[-2:]}, Given{pid[-2:]}") for pid in pids.values()
    ]
    assert len(graph.requests) == 2
    assert all(len(graph.requested_pids(request)) <= _GRAPH_FILTER_MAX_VALUES for request in graph.requests)
    assert sorted(_all_requested_pids(graph)) == sorted(pids.values())


def test_lookup_uses_signed_in_users_token_and_employee_id_filter(client, override_auth, app, bearer_token):
    graph = FakeGraph({_JANE_PID: _JANE})

    upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)

    [request] = graph.requests
    assert request.method == "GET"
    assert (request.url.host, request.url.path) == ("graph.microsoft.com", "/v1.0/users")
    assert request.headers["Authorization"] == f"Bearer {bearer_token}"
    assert request.url.params["$filter"] == f"employeeId in ('{_JANE_PID}')"
    assert request.url.params["$select"] == "employeeId,givenName,surname,displayName"


@pytest.mark.parametrize(
    ("graph", "logged_reason"),
    [
        pytest.param(FakeGraph(status_code=401), "401", id="expired-token"),
        pytest.param(FakeGraph(status_code=403), "Authorization_RequestDenied", id="permission-denied"),
        pytest.param(FakeGraph(status_code=500), "500", id="graph-error"),
        pytest.param(FakeGraph(network_error=True), "unreachable", id="network-down"),
    ],
)
def test_graph_failure_still_returns_workbook_marked_lookup_failed(
    client, override_auth, app, caplog, graph, logged_reason
):
    response, _, _ = upload(
        client, app, [FRONT, BACK, FRONT, BACK, FRONT], back_pids={1001: _JANE_PID, 1002: "730000002"}, graph=graph
    )

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [
        (_JANE_PID, _LOOKUP_FAILED),
        ("730000002", _LOOKUP_FAILED),
        ("", ""),
    ]
    rows = list(_worksheet(response).iter_rows(min_row=FIRST_DATA_ROW, values_only=True))
    assert [(amount, aid_term) for _pid, amount, _name, _directory_name, _year, aid_term, *_ in rows] == [
        (100.0, "F"),
        (200.0, "F"),
        (300.0, "F"),
    ]
    assert logged_reason in caplog.text


@pytest.mark.parametrize(
    ("given_name", "surname"),
    [
        pytest.param(None, None, id="no-given-name-or-surname"),
        pytest.param("Sam", None, id="no-surname"),
    ],
)
def test_incomplete_name_falls_back_to_display_name(client, override_auth, app, given_name, surname):
    graph = FakeGraph(
        {_JANE_PID: graph_user(_JANE_PID, given_name=given_name, surname=surname, display_name="Sam Rivera")}
    )

    response, _, _ = upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert _pid_and_directory_name_rows(response) == [(_JANE_PID, "Sam Rivera")]


def test_mixed_upload_produces_reviewable_workbook_artifact(client, override_auth, app):
    """Every outcome in one workbook, saved to tests/artifacts/ for a human to open."""
    graph = FakeGraph(
        {
            _JANE_PID: _JANE,
            "730000004": graph_user("730000004", display_name="Sam Rivera"),
            "730000006": graph_user("730000006", given_name="Chris", surname="Lee"),
        }
    )
    sides = [FRONT, BACK, FRONT, FRONT, BACK, FRONT, BACK, FRONT, BACK, FRONT, BACK]
    back_pids = {1001: _JANE_PID, 1003: "730009999", 1004: "730000004", 1005: _JANE_PID, 1006: "730000006"}

    response, _, _ = upload(client, app, sides, back_pids=back_pids, graph=graph)

    assert response.status_code == 200, response.text
    _ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    _ARTIFACT_PATH.write_bytes(response.content)
    assert _pid_and_directory_name_rows(response) == [
        (_JANE_PID, "Doe, Jane"),
        ("", ""),
        ("730009999", ""),
        ("730000004", "Sam Rivera"),
        (_JANE_PID, "Doe, Jane"),
        ("730000006", "Lee, Chris"),
    ]
    assert sorted(_all_requested_pids(graph)) == ["730000001", "730000004", "730000006", "730009999"]
