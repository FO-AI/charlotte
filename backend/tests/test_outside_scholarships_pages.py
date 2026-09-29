"""E2E: outside-scholarship uploads where some checks have no scanned back.

No real Azure access. The LLM is a fake that finds each image's page from a colour marker
PyMuPDF paints on each test page, so every assertion reflects which pages actually reached
each check: fronts carry the check number and amount, backs carry the PID.
"""

import json

import pytest

from outside_scholarships_fakes import BACK, FRONT, default_pid, preview_pid_amount_rows, upload

# A classification batch is sent up to this many times before the upload fails.
_CLASSIFICATION_ATTEMPTS = 3


@pytest.mark.parametrize(
    ("sides", "expected_rows", "expected_image_counts"),
    [
        pytest.param(
            [FRONT],
            [("", 100.0)],
            {1001: 1},
            id="single-front",
        ),
        pytest.param(
            [FRONT, BACK, FRONT],
            [(default_pid(1001), 100.0), ("", 200.0)],
            {1001: 2, 1002: 1},
            id="odd-page-count",
        ),
        pytest.param(
            [FRONT, BACK, FRONT, FRONT, BACK],
            [(default_pid(1001), 100.0), ("", 200.0), (default_pid(1003), 300.0)],
            {1001: 2, 1002: 1, 1003: 2},
            id="missing-back-in-middle",
        ),
        pytest.param(
            [FRONT, FRONT, FRONT, FRONT],
            [("", 100.0), ("", 200.0), ("", 300.0), ("", 400.0)],
            {1001: 1, 1002: 1, 1003: 1, 1004: 1},
            id="all-fronts-even-count",
        ),
        pytest.param(
            [FRONT, BACK, FRONT, BACK],
            [(default_pid(1001), 100.0), (default_pid(1002), 200.0)],
            {1001: 2, 1002: 2},
            id="every-check-has-back",
        ),
    ],
)
def test_pages_group_into_checks_by_detected_side(
    client, override_auth, app, sides, expected_rows, expected_image_counts
):
    response, llm = upload(client, app, sides)

    assert response.status_code == 200, response.text
    assert preview_pid_amount_rows(response) == expected_rows
    assert llm.image_counts_by_check() == expected_image_counts


@pytest.mark.parametrize(
    ("sides", "orphan_page"),
    [
        pytest.param([BACK, FRONT], 1, id="leading-back"),
        pytest.param([FRONT, BACK, BACK], 3, id="two-backs-in-a-row"),
    ],
)
def test_back_without_front_is_rejected_with_page_number(client, override_auth, app, sides, orphan_page):
    response, llm = upload(client, app, sides)

    assert response.status_code == 400
    assert f"Page {orphan_page} " in response.json()["detail"]
    assert llm.extraction_calls == 0


@pytest.mark.parametrize(
    "classify_reply",
    [
        pytest.param(lambda pages: "not json", id="not-json"),
        pytest.param(
            lambda pages: json.dumps({"pages": [{"page": page, "side": FRONT} for page in pages[:-1]]}),
            id="page-missing",
        ),
        pytest.param(
            lambda pages: json.dumps({"pages": [{"page": page, "side": "sideways"} for page in pages]}),
            id="unknown-side",
        ),
    ],
)
def test_invalid_classifier_reply_fails_before_extraction(client, override_auth, app, classify_reply):
    response, llm = upload(client, app, [FRONT, BACK], classify_reply=classify_reply)

    assert response.status_code == 500
    assert llm.extraction_calls == 0
    assert llm.classified_pages == [[1, 2]] * _CLASSIFICATION_ATTEMPTS


@pytest.mark.parametrize("failed_attempts", [1, _CLASSIFICATION_ATTEMPTS - 1])
def test_invalid_classifier_reply_is_retried_for_that_batch(
    client, override_auth, app, caplog, failed_attempts
):
    sides = [FRONT, BACK] * 6
    second_batch = [11, 12]
    second_batch_replies = []

    def second_batch_drops_a_page_at_first(pages):
        listed = pages
        if pages == second_batch:
            second_batch_replies.append(pages)
            if len(second_batch_replies) <= failed_attempts:
                listed = pages[1:]
        return json.dumps({"pages": [{"page": page, "side": sides[page - 1]} for page in listed]})

    response, llm = upload(client, app, sides, classify_reply=second_batch_drops_a_page_at_first)

    assert response.status_code == 200, response.text
    assert sorted(llm.classified_pages) == [list(range(1, 11))] + [second_batch] * (failed_attempts + 1)
    assert [pid for pid, _ in preview_pid_amount_rows(response)] == [default_pid(1000 + i) for i in range(1, 7)]
    assert "retrying" in caplog.text


def test_classifier_formatting_variations_are_accepted(client, override_auth, app):
    sides = [FRONT, BACK, FRONT]

    def loosely_formatted_reply(pages):
        return json.dumps(
            {"pages": [{"page": str(page), "side": f" {sides[page - 1].title()} "} for page in pages]}
        )

    response, _ = upload(client, app, sides, classify_reply=loosely_formatted_reply)

    assert response.status_code == 200, response.text
    assert preview_pid_amount_rows(response) == [(default_pid(1001), 100.0), ("", 200.0)]


def test_pages_beyond_one_batch_keep_pdf_page_numbers(client, override_auth, app):
    sides = [FRONT, BACK] * 6

    response, llm = upload(client, app, sides)

    assert response.status_code == 200, response.text
    assert sorted(llm.classified_pages) == [list(range(1, 11)), [11, 12]]
    assert [pid for pid, _ in preview_pid_amount_rows(response)] == [default_pid(1000 + i) for i in range(1, 7)]


def test_preview_includes_page_numbers_and_jpeg_images(client, override_auth, app):
    response, _ = upload(client, app, [FRONT, BACK, FRONT])

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["aid_term"] == "F"
    assert len(payload["checks"]) == 2
    first, second = payload["checks"]
    assert first["front_page"] == 1
    assert first["back_page"] == 2
    assert first["front_image"].startswith("data:image/jpeg;base64,")
    assert first["back_image"].startswith("data:image/jpeg;base64,")
    assert second["front_page"] == 3
    assert second["back_page"] is None
    assert second["front_image"].startswith("data:image/jpeg;base64,")
    assert second["back_image"] is None
