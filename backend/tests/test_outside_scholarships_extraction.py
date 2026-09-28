"""E2E: each check's fields come from one vision-LLM call on its images, with no Document Intelligence pass.

Ways LLM-only extraction can fail, each guarded here or in the neighbouring outside-scholarship tests:
1. The upload still needs Document Intelligence and fails with 500 "Document Intelligence client
   is not configured". Every outside-scholarship test's fake Azure client has only an LLM, so any
   Document Intelligence path left in the pipeline fails them all.
2. A field the model returns never reaches the workbook (amount, payee name, provider,
   scholarship name).
3. A check is read from the wrong pages or at thumbnail resolution. The fake LLM finds each
   image's page from a colour marker and fails any call that is not one front plus, at most, the
   back right after it; test_outside_scholarships_concurrency checks the resolution.
4. A number that is not a PID (an approval or check number, a 7- or 10-digit run) reaches the PID
   column and the Active Directory lookup. Or a real nine-digit PID written with separators
   ("730-000-001", "P730000001") or returned as a bare JSON value is dropped instead of normalized.
5. Rows come out in the order extractions finish instead of check order
   (test_outside_scholarships_concurrency).
6. An unreadable reply for one check is written as an empty row instead of failing the upload.
7. More extraction calls run at once than MAX_CONCURRENT_CHECKS (test_outside_scholarships_concurrency).

No real Azure or Graph access (see outside_scholarships_fakes.py). The mixed-upload test saves its
workbook to tests/artifacts/ for a human to open.
"""

import json
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from outside_scholarships_fakes import BACK, FIRST_DATA_ROW, FRONT, FakeGraph, graph_user, upload

_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "outside_scholarships_llm_extraction.xlsx"
_AID_YEAR = str(date.today().year)
_JANE_PID = "730001001"
_JANE = graph_user(_JANE_PID, given_name="Jane", surname="Doe")


def _rows(response):
    worksheet = load_workbook(BytesIO(response.content)).active
    return [
        tuple("" if cell is None else cell for cell in row)
        for row in worksheet.iter_rows(min_row=FIRST_DATA_ROW, values_only=True)
    ]


def _pids(response):
    return [row[0] for row in _rows(response)]


def test_mixed_upload_fills_every_column_from_the_extraction(client, override_auth, app):
    """Every column in one workbook, saved to tests/artifacts/ for review."""
    graph = FakeGraph({_JANE_PID: _JANE})
    sides = [FRONT, BACK, FRONT, FRONT, BACK]
    # Check 1003's back carries two PIDs and an approval number, which must not become a row.
    back_pids = {1001: _JANE_PID, 1003: ["730001003", "730-001-013", "12345678"]}

    response, llm = upload(client, app, sides, back_pids=back_pids, graph=graph)

    assert response.status_code == 200, response.text
    _ARTIFACT_PATH.parent.mkdir(exist_ok=True)
    _ARTIFACT_PATH.write_bytes(response.content)
    assert llm.image_counts_by_check() == {1001: 2, 1002: 1, 1003: 2}
    assert _rows(response) == [
        (_JANE_PID, 100.0, "Payee 1001", "Doe, Jane", _AID_YEAR, "F", "Provider 1001", "Scholarship 1001"),
        ("", 200.0, "Payee 1002", "", _AID_YEAR, "F", "Provider 1002", "Scholarship 1002"),
        ("730001003", 300.0, "Payee 1003", "", _AID_YEAR, "F", "Provider 1003", "Scholarship 1003"),
        ("730001013", 300.0, "Payee 1003", "", _AID_YEAR, "F", "Provider 1003", "Scholarship 1003"),
    ]


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
    # The fake LLM's own pairing checks also end in this 500; the log shows which failure it was.
    assert f"Field extraction for check 2 {logged_reason}" in caplog.text
