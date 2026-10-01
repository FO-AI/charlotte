"""E2E: the Active Directory Name on each preview PID comes from Microsoft Graph.

Runs the real route, extraction graph and Graph lookup. The LLM and Graph are faked.
"""

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from outside_scholarships_fakes import (
    BACK,
    FRONT,
    LOOKUP_ROUTE,
    REVIEW_FIRST_DATA_ROW,
    REVIEW_HEADER_ROW,
    FakeGraph,
    export_excel,
    graph_user,
    preview_payload,
    preview_pid_and_directory_name_rows,
    upload,
)

_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "outside_scholarships_active_directory_names.xlsx"
_LOOKUP_FAILED = "Lookup failed"
_GRAPH_FILTER_MAX_VALUES = 15

_JANE_PID = "730000001"
_JANE = graph_user(_JANE_PID, given_name="Jane", surname="Doe", display_name="Jane Doe")


def _all_requested_pids(graph):
    return [pid for request in graph.requests for pid in graph.requested_pids(request)]


def test_preview_pids_include_active_directory_status(client, override_auth, app):
    response, _ = upload(client, app, [FRONT])

    assert response.status_code == 200, response.text
    payload = preview_payload(response)
    assert payload["checks"][0]["pids"] == []


def test_pid_found_in_directory_gets_last_first_name(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _ = upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane")]
    entry = preview_payload(response)["checks"][0]["pids"][0]
    assert entry["active_directory"] == {"status": "found", "name": "Doe, Jane"}


def test_pid_missing_from_directory_is_blank(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _ = upload(client, app, [FRONT, BACK], back_pids={1001: "730009999"}, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [("730009999", "")]
    assert preview_payload(response)["checks"][0]["pids"][0]["active_directory"]["status"] == "not_found"


def test_check_without_pid_is_blank_and_not_looked_up(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _ = upload(client, app, [FRONT, BACK, FRONT], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane"), ("", "")]
    assert _all_requested_pids(graph) == [_JANE_PID]


def test_upload_without_pids_makes_no_graph_request(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _ = upload(client, app, [FRONT, FRONT], graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [("", ""), ("", "")]
    assert graph.requests == []


def test_repeated_pid_is_looked_up_once_and_filled_on_every_row(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})

    response, _ = upload(
        client, app, [FRONT, BACK, FRONT, BACK], back_pids={1001: _JANE_PID, 1002: _JANE_PID}, graph=graph
    )

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [(_JANE_PID, "Doe, Jane"), (_JANE_PID, "Doe, Jane")]
    assert _all_requested_pids(graph) == [_JANE_PID]


def test_more_than_fifteen_pids_are_split_across_requests(client, override_auth, app):
    check_count = _GRAPH_FILTER_MAX_VALUES + 1
    pids = {1000 + index: f"7300000{index:02d}" for index in range(1, check_count + 1)}
    graph = FakeGraph(
        {pid: graph_user(pid, given_name=f"Given{pid[-2:]}", surname=f"Surname{pid[-2:]}") for pid in pids.values()}
    )

    response, _ = upload(client, app, [FRONT, BACK] * check_count, back_pids=pids, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [
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
def test_graph_failure_still_returns_preview_marked_lookup_failed(
    client, override_auth, app, caplog, graph, logged_reason
):
    response, _ = upload(
        client, app, [FRONT, BACK, FRONT, BACK, FRONT], back_pids={1001: _JANE_PID, 1002: "730000002"}, graph=graph
    )

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [
        (_JANE_PID, _LOOKUP_FAILED),
        ("730000002", _LOOKUP_FAILED),
        ("", ""),
    ]
    checks = preview_payload(response)["checks"]
    assert checks[0]["pids"][0]["active_directory"]["status"] == "lookup_failed"
    assert checks[1]["pids"][0]["active_directory"]["status"] == "lookup_failed"
    assert [float(check["amount"]) for check in checks] == [100.0, 200.0, 300.0]
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

    response, _ = upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [(_JANE_PID, "Sam Rivera")]


def test_active_directory_lookup_endpoint(client, override_auth, app, bearer_token):
    from api.dependencies import get_azure_client, get_graph_user_directory
    from services.azure_services import GraphUserDirectory
    from types import SimpleNamespace

    graph = FakeGraph({_JANE_PID: _JANE})
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=None)
    app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(transport=graph.transport)

    response = client.post(LOOKUP_ROUTE, json={"pids": [_JANE_PID, "730009999"]})

    assert response.status_code == 200, response.text
    by_pid = {entry["pid"]: entry["active_directory"] for entry in response.json()["pids"]}
    assert by_pid[_JANE_PID] == {"status": "found", "name": "Doe, Jane"}
    assert by_pid["730009999"] == {"status": "not_found", "name": None}
    assert graph.requests[0].headers["Authorization"] == f"Bearer {bearer_token}"


def test_export_writes_reviewed_by_and_audit_columns(client, override_auth, app):
    from types import SimpleNamespace

    from api.dependencies import get_azure_client, get_graph_user_directory
    from services.azure_services import GraphUserDirectory

    graph = FakeGraph({_JANE_PID: _JANE})
    response, _ = upload(client, app, [FRONT, BACK], back_pids={1001: _JANE_PID}, graph=graph)
    preview = preview_payload(response)

    export_body = {
        "aid_year": preview["aid_year"],
        "aid_term": preview["aid_term"],
        "checks": [
            {
                "check_index": 1,
                "extracted": {
                    "amount": "100.00",
                    "check_number": "1001",
                    "name": "Payee 1001",
                    "provider": "Provider 1001",
                    "scholarship_name": "Scholarship 1001",
                    "pids": [{"pid": _JANE_PID, "active_directory": {"status": "found", "name": "Spoofed, Name"}}],
                },
                "reviewed": {
                    "amount": "1 250.00",
                    "check_number": "1001",
                    "name": "=HYPERLINK(\"http://evil\")",
                    "provider": "Provider 1001",
                    "scholarship_name": "Scholarship 1001",
                    "pids": [
                        {"pid": _JANE_PID, "active_directory": {"status": "found", "name": "Spoofed, Name"}},
                        {"pid": "730000099", "active_directory": {"status": "found", "name": "Also Spoofed"}},
                    ],
                },
                "verified": True,
            }
        ],
    }
    app.dependency_overrides[get_azure_client] = lambda: SimpleNamespace(llm=None)
    app.dependency_overrides[get_graph_user_directory] = lambda: GraphUserDirectory(transport=graph.transport)

    export_response = client.post("/api/banking/outside-scholarships/export", json=export_body)
    assert export_response.status_code == 200, export_response.text
    worksheet = load_workbook(BytesIO(export_response.content)).active
    assert [cell.value for cell in worksheet[REVIEW_HEADER_ROW]][:12] == [
        "PID",
        "Amount",
        "Check #",
        "Name",
        "Active Directory Name",
        "Aid year",
        "Aid term",
        "Provider",
        "Scholarship name",
        "Edited",
        "Verified",
        "Extracted values",
    ]
    assert worksheet["A4"].value == "Reviewed by"
    rows = list(worksheet.iter_rows(min_row=REVIEW_FIRST_DATA_ROW, values_only=True))
    assert rows[0][0] == _JANE_PID
    assert rows[0][1] == 1250.0
    assert rows[0][2] == "1001"
    assert rows[0][3] == "'=HYPERLINK(\"http://evil\")"
    assert rows[0][4] == "Doe, Jane"
    assert rows[0][9] == "Yes"
    assert rows[0][10] == "Yes"
    assert "Amount: 100.00" in rows[0][11]
    assert "Added PID: 730000099" in rows[0][11]
    assert rows[1][0] == "730000099"
    assert rows[1][2] == "1001"
    assert not rows[1][4]

    assert worksheet.data_validations.dataValidation, "expected Provider text-length validation"
    rule = worksheet.data_validations.dataValidation[0]
    assert rule.type == "textLength"
    assert rule.operator == "between"
    assert str(rule.formula1) == "1"
    assert str(rule.formula2) == "30"
    assert str(rule.sqref).startswith("H"), rule.sqref


def test_mixed_upload_produces_reviewable_workbook_artifact(client, override_auth, app):
    graph = FakeGraph(
        {
            _JANE_PID: _JANE,
            "730000004": graph_user("730000004", display_name="Sam Rivera"),
            "730000006": graph_user("730000006", given_name="Chris", surname="Lee"),
        }
    )
    sides = [FRONT, BACK, FRONT, FRONT, BACK, FRONT, BACK, FRONT, BACK, FRONT, BACK]
    back_pids = {1001: _JANE_PID, 1003: "730009999", 1004: "730000004", 1005: _JANE_PID, 1006: "730000006"}

    response, _ = upload(client, app, sides, back_pids=back_pids, graph=graph)

    assert response.status_code == 200, response.text
    assert preview_pid_and_directory_name_rows(response) == [
        (_JANE_PID, "Doe, Jane"),
        ("", ""),
        ("730009999", ""),
        ("730000004", "Sam Rivera"),
        (_JANE_PID, "Doe, Jane"),
        ("730000006", "Lee, Chris"),
    ]
    export_response = export_excel(
        client,
        app,
        preview_payload(response),
        verified_indexes={2},
        graph=graph,
    )
    assert export_response.status_code == 200, export_response.text
    _ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    _ARTIFACT_PATH.write_bytes(export_response.content)
    worksheet = load_workbook(BytesIO(export_response.content)).active
    excel_pids = [
        pid or ""
        for pid, *_ in worksheet.iter_rows(min_row=REVIEW_FIRST_DATA_ROW, values_only=True)
    ]
    assert excel_pids == [_JANE_PID, "", "730009999", "730000004", _JANE_PID, "730000006"]
    # Upload + export each look up AD; compare the distinct PIDs asked of Graph.
    assert sorted(set(_all_requested_pids(graph))) == ["730000001", "730000004", "730000006", "730009999"]
