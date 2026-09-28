"""E2E: outside-scholarship uploads stay correct when their slow steps run concurrently.

Ways the concurrent pipeline can fail, each guarded below:
1. Side-classification batches still go out one after another, so a large PDF waits on
   one LLM call per ten pages before any check starts.
2. Batch replies are stitched together in completion order instead of page order, so a slow
   early batch shifts every later page and checks get the wrong fronts and backs.
3. More extraction calls run at once than the per-upload cap, beyond the Azure OpenAI
   deployment's rate limit, or a large PDF sends every side-classification batch at once,
   beyond that same cap.
4. With rendering in the per-check workers, a check is extracted at the wrong resolution
   (such as the classification thumbnail) or without its back.
5. Checks finishing extraction out of order put their workbook rows out of check order.
6. PyMuPDF is used from several threads at once, which it does not support. The pipeline
   serializes it with PYMUPDF_LOCK; the fake LLM takes the same lock when it reads images.

No real Azure or Graph access (see outside_scholarships_fakes.py). Timing properties are
checked structurally (barriers and in-flight counters), never with wall-clock thresholds.
"""

import threading

import fitz
import pytest

from outside_scholarships_fakes import BACK, FIRST_CHECK_NUMBER, FRONT, default_pid, upload
from services.banking.outside_scholarships.nodes import PYMUPDF_LOCK
from services.banking.outside_scholarships.service import MAX_CONCURRENT_CHECKS

_CLASSIFICATION_BATCH_SIZE = 10
_EXTRACTION_DPI = 200
_BARRIER_TIMEOUT_SECONDS = 5
_HELD_CALL_SECONDS = 0.2
_EXTRACTION_STAGGER_SECONDS = 0.1


def _expected_images_per_check(sides):
    counts = {}
    check_number = FIRST_CHECK_NUMBER - 1
    for side in sides:
        if side == FRONT:
            check_number += 1
            counts[check_number] = 1
        else:
            counts[check_number] = 2
    return counts


def test_classification_batches_are_sent_concurrently(client, override_auth, app):
    sides = [FRONT] * (3 * _CLASSIFICATION_BATCH_SIZE)
    # Sent one after another, the first batch waits alone until the barrier times out.
    barrier = threading.Barrier(parties=3, timeout=_BARRIER_TIMEOUT_SECONDS)

    response, llm = upload(client, app, sides, classification_barrier=barrier)

    assert response.status_code == 200, response.text
    assert llm.extraction_calls == len(sides)


def test_batches_finishing_out_of_order_keep_page_order(client, override_auth, app):
    # Three batches with different side patterns, so any reordering changes the checks.
    sides = (
        [FRONT, BACK] * 5
        + [FRONT] * 10
        + [FRONT, BACK] + [FRONT] * 8
    )
    finish_last_first = {1: 0.4, 11: 0.2, 21: 0.0}

    response, llm = upload(
        client, app, sides, classification_delay=lambda first_page: finish_last_first[first_page]
    )

    assert response.status_code == 200, response.text
    assert llm.image_counts_by_check() == _expected_images_per_check(sides)


def test_extraction_calls_stay_within_the_concurrency_cap(client, override_auth, app):
    sides = [FRONT] * (3 * MAX_CONCURRENT_CHECKS)

    response, llm = upload(client, app, sides, extraction_delay=lambda check_number: _HELD_CALL_SECONDS)

    assert response.status_code == 200, response.text
    assert 1 < llm.extractions.peak <= MAX_CONCURRENT_CHECKS


def test_classification_calls_stay_within_the_concurrency_cap(client, override_auth, app):
    sides = [FRONT] * (_CLASSIFICATION_BATCH_SIZE * (MAX_CONCURRENT_CHECKS + 2))

    response, llm = upload(client, app, sides, classification_delay=lambda first_page: _HELD_CALL_SECONDS)

    assert response.status_code == 200, response.text
    assert 1 < llm.classifications.peak <= MAX_CONCURRENT_CHECKS


def test_rows_keep_check_order_when_extractions_finish_out_of_order(client, override_auth, app):
    from outside_scholarships_fakes import preview_pid_amount_rows

    check_count = 4
    last_check = FIRST_CHECK_NUMBER + check_count - 1

    # The first check's extraction finishes last, the last check's first.
    response, _ = upload(
        client,
        app,
        [FRONT, BACK] * check_count,
        extraction_delay=lambda check_number: (last_check - check_number) * _EXTRACTION_STAGGER_SECONDS,
    )

    assert response.status_code == 200, response.text
    pids = [pid for pid, _ in preview_pid_amount_rows(response)]
    assert pids == [default_pid(FIRST_CHECK_NUMBER + offset) for offset in range(check_count)]


@pytest.mark.parametrize(
    ("sides", "expected_page_counts"),
    [
        pytest.param([FRONT, BACK, FRONT], {1001: 2, 1002: 1}, id="back-then-no-back"),
        pytest.param([FRONT, FRONT, BACK], {1001: 1, 1002: 2}, id="no-back-then-back"),
    ],
)
def test_checks_are_extracted_from_full_resolution_pages(client, override_auth, app, sides, expected_page_counts):
    response, llm = upload(client, app, sides)

    assert response.status_code == 200, response.text
    with PYMUPDF_LOCK, fitz.open() as blank:
        page_rect = blank.new_page().rect
    scale = _EXTRACTION_DPI / 72
    rendered = (page_rect * fitz.Matrix(scale, scale)).irect
    full_resolution = (rendered.width, rendered.height)
    assert llm.image_sizes_by_check == {
        check: [full_resolution] * page_count for check, page_count in expected_page_counts.items()
    }
