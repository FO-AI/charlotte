"""Supporting pages stay with the check ahead of them and do not replace the check's money or PID."""

from io import BytesIO

import pytest
from openpyxl import load_workbook

from outside_scholarships_fakes import (
    BACK,
    FRONT,
    REVIEW_FIRST_DATA_ROW,
    SUPPORTING,
    export_excel,
    preview_payload,
    upload,
)
from prompts.outside_scholarship import EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT
from services.banking.outside_scholarships.nodes import _group_pages_by_check, _normalize_aid_term


def test_grouping_checks_in_a_row_with_no_supporting_pages():
    assert _group_pages_by_check([FRONT, FRONT, BACK, FRONT]) == [
        {"front": 0, "back": None, "supporting": []},
        {"front": 1, "back": 2, "supporting": []},
        {"front": 3, "back": None, "supporting": []},
    ]


def test_grouping_check_with_several_supporting_pages():
    assert _group_pages_by_check([FRONT, SUPPORTING, SUPPORTING, FRONT, SUPPORTING]) == [
        {"front": 0, "back": None, "supporting": [1, 2]},
        {"front": 3, "back": None, "supporting": [4]},
    ]


def test_grouping_front_back_then_supporting():
    assert _group_pages_by_check([FRONT, BACK, SUPPORTING, SUPPORTING]) == [
        {"front": 0, "back": 1, "supporting": [2, 3]},
    ]


def test_grouping_rejects_a_supporting_page_before_any_check():
    with pytest.raises(ValueError, match="no check before it"):
        _group_pages_by_check([SUPPORTING, FRONT])


def test_grouping_keeps_a_back_that_was_scanned_after_a_supporting_page():
    assert _group_pages_by_check([FRONT, SUPPORTING, BACK, SUPPORTING]) == [
        {"front": 0, "back": 2, "supporting": [1, 3]},
    ]


def test_a_back_scanned_after_a_stub_is_still_the_check_back(client, override_auth, app):
    response, llm = upload(
        client,
        app,
        [FRONT, SUPPORTING, BACK],
        back_pids={1001: "730000001"},
    )
    assert response.status_code == 200, response.text
    check = preview_payload(response)["checks"][0]
    assert check["front_page"] == 1
    assert check["back_page"] == 3
    assert check["supporting_pages"] == [2]
    assert [entry["pid"] for entry in check["pids"]] == ["730000001"]
    assert llm.image_counts_by_check()[1001] == 3


def test_grouping_rejects_a_second_back():
    with pytest.raises(ValueError, match="only one back"):
        _group_pages_by_check([FRONT, BACK, BACK])


def test_normalize_aid_term_drops_wording_that_is_not_a_code():
    assert _normalize_aid_term("F/S") == "F/S"
    assert _normalize_aid_term(" ss2 ") == "SS2"
    assert _normalize_aid_term("Fall 2026 and Spring 2027") is None
    assert _normalize_aid_term(None) is None


def test_prompt_ignores_an_unmarked_option_list():
    assert "if not indicated, we will split evenly" in EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT
    assert "printed list of options is not a selection" in EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT
    assert "Do not add a PID that appears only on a supporting page" in EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT


def test_supporting_pages_fill_name_scholarship_and_term_without_replacing_amount_or_pid(
    client, override_auth, app
):
    response, llm = upload(
        client,
        app,
        [FRONT, BACK, SUPPORTING, SUPPORTING, FRONT],
        back_pids={1001: "730000001"},
        supporting_by_page={
            3: {
                "scholarship_name": "Wells Fargo Employees Scholarship",
                "student_name": "Ella Kate DeLapp",
                "aid_term": "F/S",
                "supporting_amount": "9999.00",
                "supporting_pid": "730999999",
            },
            4: {
                "aid_term": None,
                "supporting_amount": "10000.00",
            },
        },
        aid_term="F",
    )
    assert response.status_code == 200, response.text
    preview = preview_payload(response)
    first, second = preview["checks"]
    assert first["amount"] == "100.00"
    assert [entry["pid"] for entry in first["pids"]] == ["730000001"]
    assert first["name"] == "Ella Kate DeLapp"
    assert first["scholarship_name"] == "Wells Fargo Employees Scholarship"
    assert first["aid_term"] == "F/S"
    assert first["supporting_pages"] == [3, 4]
    assert len(first["supporting_images"]) == 2
    assert all(image.startswith("data:image/jpeg;base64,") for image in first["supporting_images"])
    assert llm.image_counts_by_check()[1001] == 4
    assert second["aid_term"] is None
    assert second["supporting_images"] == []
    assert second["amount"] == "200.00"

    export_response = export_excel(client, app, preview)
    assert export_response.status_code == 200, export_response.text
    worksheet = load_workbook(BytesIO(export_response.content)).active
    rows = list(worksheet.iter_rows(min_row=REVIEW_FIRST_DATA_ROW, values_only=True))
    assert rows[0][6] == "F/S"
    assert rows[1][6] == "F"


def _excel_amounts(response):
    worksheet = load_workbook(BytesIO(response.content)).active
    return [
        row[1]
        for row in worksheet.iter_rows(min_row=REVIEW_FIRST_DATA_ROW, values_only=True)
    ]


def test_complete_supporting_pid_amount_split_reaches_preview_and_excel(client, override_auth, app):
    response, _ = upload(
        client,
        app,
        [FRONT, BACK, SUPPORTING, SUPPORTING, SUPPORTING, SUPPORTING],
        back_pids={1001: ["730000001", "730000002", "730000003"]},
        supporting_by_page={
            3: {"supporting_pid": "730000001", "supporting_amount": "30.00"},
            4: {"supporting_pid": "730000002", "supporting_amount": "30.00"},
            5: {"supporting_pid": "730000003", "supporting_amount": "40.00"},
            6: {"supporting_pid": "730999999", "supporting_amount": "999.00"},
        },
    )
    assert response.status_code == 200, response.text

    preview = preview_payload(response)
    pids = preview["checks"][0]["pids"]
    assert [(entry["pid"], entry["amount"]) for entry in pids] == [
        ("730000001", "30.00"),
        ("730000002", "30.00"),
        ("730000003", "40.00"),
    ]

    export_response = export_excel(client, app, preview)
    assert export_response.status_code == 200, export_response.text
    assert _excel_amounts(export_response) == [30, 30, 40]


def test_incomplete_supporting_pid_amount_split_exports_full_check_amount(client, override_auth, app):
    response, _ = upload(
        client,
        app,
        [FRONT, BACK, SUPPORTING, SUPPORTING],
        back_pids={1001: ["730000001", "730000002", "730000003"]},
        supporting_by_page={
            3: {"supporting_pid": "730000001", "supporting_amount": "30.00"},
            4: {"supporting_pid": "730000002", "supporting_amount": "30.00"},
        },
    )
    assert response.status_code == 200, response.text

    preview = preview_payload(response)
    assert [entry.get("amount") for entry in preview["checks"][0]["pids"]] == [
        "30.00",
        "30.00",
        None,
    ]

    export_response = export_excel(client, app, preview)
    assert export_response.status_code == 200, export_response.text
    assert _excel_amounts(export_response) == [100, 100, 100]


def test_mismatched_supporting_pid_amount_split_exports_full_check_amount(client, override_auth, app):
    response, _ = upload(
        client,
        app,
        [FRONT, BACK, SUPPORTING, SUPPORTING, SUPPORTING],
        back_pids={1001: ["730000001", "730000002", "730000003"]},
        supporting_by_page={
            3: {"supporting_pid": "730000001", "supporting_amount": "30.00"},
            4: {"supporting_pid": "730000002", "supporting_amount": "30.00"},
            5: {"supporting_pid": "730000003", "supporting_amount": "30.00"},
        },
    )
    assert response.status_code == 200, response.text

    preview = preview_payload(response)
    export_response = export_excel(client, app, preview)
    assert export_response.status_code == 200, export_response.text
    assert _excel_amounts(export_response) == [100, 100, 100]
