"""E2E: each check's fields come from one vision-LLM call on its images, with no Document Intelligence pass.

No real Azure or Graph access (see outside_scholarships_fakes.py). Preview JSON is asserted
directly; the mixed-upload test also exports Excel to tests/artifacts/ for review.
"""

import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from outside_scholarships_fakes import (
    BACK,
    FRONT,
    FakeGraph,
    REVIEW_FIRST_DATA_ROW,
    export_excel,
    graph_user,
    preview_payload,
    upload,
)

_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "outside_scholarships_llm_extraction.xlsx"
_AID_YEAR = str(date.today().year)
_JANE_PID = "730001001"
_JANE = graph_user(_JANE_PID, given_name="Jane", surname="Doe")


def _preview_rows(response):
    rows = []
    for check in preview_payload(response)["checks"]:
        pids = check.get("pids") or []
        amount = float(check["amount"]) if check.get("amount") is not None else 0.0
        ad_name = ""
        name = check.get("name") or ""
        provider = check.get("provider") or ""
        scholarship = check.get("scholarship_name") or ""
        year = preview_payload(response)["aid_year"]
        term = preview_payload(response)["aid_term"]
        if not pids:
            rows.append(("", amount, name, "", year, term, provider, scholarship))
            continue
        for entry in pids:
            ad = entry.get("active_directory") or {}
            if ad.get("status") == "found":
                ad_name = ad.get("name") or ""
            elif ad.get("status") == "lookup_failed":
                ad_name = "Lookup failed"
            else:
                ad_name = ""
            rows.append((entry.get("pid") or "", amount, name, ad_name, year, term, provider, scholarship))
    return rows


def _pids(response):
    return [row[0] for row in _preview_rows(response)]


def test_mixed_upload_fills_every_column_from_the_extraction(client, override_auth, app):
    graph = FakeGraph({_JANE_PID: _JANE})
    sides = [FRONT, BACK, FRONT, FRONT, BACK]
    back_pids = {1001: _JANE_PID, 1003: ["730001003", "730-001-013", "12345678"]}

    response, llm = upload(client, app, sides, back_pids=back_pids, graph=graph)

    assert response.status_code == 200, response.text
    assert llm.image_counts_by_check() == {1001: 2, 1002: 1, 1003: 2}
    assert _preview_rows(response) == [
        (_JANE_PID, 100.0, "Payee 1001", "Doe, Jane", _AID_YEAR, "F", "Provider 1001", "Scholarship 1001"),
        ("", 200.0, "Payee 1002", "", _AID_YEAR, "F", "Provider 1002", "Scholarship 1002"),
        ("730001003", 300.0, "Payee 1003", "", _AID_YEAR, "F", "Provider 1003", "Scholarship 1003"),
        ("730001013", 300.0, "Payee 1003", "", _AID_YEAR, "F", "Provider 1003", "Scholarship 1003"),
    ]

    export_response = export_excel(client, app, preview_payload(response), verified_indexes={2}, graph=graph)
    assert export_response.status_code == 200, export_response.text
    _ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    _ARTIFACT_PATH.write_bytes(export_response.content)
    worksheet = load_workbook(BytesIO(export_response.content)).active
    assert worksheet["A4"].value == "Reviewed by"
    excel_rows = list(worksheet.iter_rows(min_row=REVIEW_FIRST_DATA_ROW, values_only=True))
    assert [(row[0] or "") for row in excel_rows] == [_JANE_PID, "", "730001003", "730001013"]


@pytest.mark.parametrize(
    ("written_pids", "expected_pids"),
    [
        pytest.param(["730-000-001"], ["730000001"], id="dashes-normalized"),
        pytest.param(["P730000002"], ["730000002"], id="prefix-normalized"),
        pytest.param(["730 000 003"], ["730000003"], id="spaces-normalized"),
        pytest.param(["12345678"], [], id="eight-digits-dropped"),
        pytest.param(["7300000044"], [], id="ten-digits-dropped"),
        pytest.param(["1001"], [], id="check-number-dropped"),
        pytest.param(["APPROVED"], [], id="no-digits-dropped"),
        pytest.param(["7300000055", "730000005", "730000005"], ["730000005"], id="duplicate-kept-once"),
    ],
)
def test_only_nine_digit_pids_reach_the_workbook_and_directory(
    client, override_auth, app, written_pids, expected_pids
):
    graph = FakeGraph()

    response, _ = upload(client, app, [FRONT, BACK], back_pids={1001: written_pids}, graph=graph)

    assert response.status_code == 200, response.text
    assert _pids(response) == (expected_pids or [""])
    assert graph.all_requested_pids() == expected_pids


@pytest.mark.parametrize(
    "bare_pid",
    [
        pytest.param(730001001, id="json-number"),
        pytest.param("730001001", id="json-string"),
    ],
)
def test_single_pid_returned_without_a_list_is_kept(client, override_auth, app, bare_pid):
    def bare_pid_reply(check_number, fields):
        return json.dumps({**fields, "pid_list": bare_pid})

    response, _ = upload(client, app, [FRONT, BACK], extraction_reply=bare_pid_reply)

    assert response.status_code == 200, response.text
    assert _pids(response) == ["730001001"]


@pytest.mark.parametrize(
    ("reply", "logged_reason"),
    [
        pytest.param("not json", "returned an unreadable reply", id="not-json"),
        pytest.param('["730001002"]', "returned list, not an object", id="json-list"),
    ],
)
def test_unreadable_reply_for_one_check_fails_the_upload(client, override_auth, app, caplog, reply, logged_reason):
    def unreadable_second_check(check_number, fields):
        return reply if check_number == 1002 else json.dumps(fields)

    response, _ = upload(client, app, [FRONT, BACK, FRONT, BACK], extraction_reply=unreadable_second_check)

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to process outside scholarship PDF."
    assert f"Field extraction for check 2 {logged_reason}" in caplog.text
