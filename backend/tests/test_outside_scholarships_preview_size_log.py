"""Preview size log must count front_image/back_image data URLs (not legacy preview keys)."""

import logging
import re

from outside_scholarships_fakes import BACK, FRONT, preview_payload, upload
from services.banking.outside_scholarships.service import OutsideScholarshipService


def test_preview_image_char_count_uses_front_and_back_image_keys():
    checks = [
        {
            "front_image": "data:image/jpeg;base64,aaa",
            "back_image": "data:image/jpeg;base64,bbbb",
            "front_preview": "x" * 1000,
            "back_preview": "y" * 1000,
        },
        {"front_image": "data:image/jpeg;base64,cc", "back_image": None},
        "skip-me",
    ]
    # Legacy front_preview/back_preview keys must not contribute to the total.
    assert OutsideScholarshipService._preview_image_char_count(checks) == (
        len("data:image/jpeg;base64,aaa")
        + len("data:image/jpeg;base64,bbbb")
        + len("data:image/jpeg;base64,cc")
    )
    assert OutsideScholarshipService._preview_image_char_count([]) == 0
    assert OutsideScholarshipService._preview_image_char_count(None) == 0


def test_upload_logs_nonzero_preview_image_chars(client, override_auth, app, caplog):
    with caplog.at_level(logging.INFO, logger="services.banking.outside_scholarships.service"):
        response, _llm = upload(client, app, [FRONT, BACK])

    assert response.status_code == 200, response.text
    preview = preview_payload(response)
    direct_count = OutsideScholarshipService._preview_image_char_count(preview["checks"])
    assert direct_count > 0
    assert preview["checks"][0]["front_image"].startswith("data:image/jpeg;base64,")
    assert preview["checks"][0].get("front_preview") is None

    logged = [
        record.getMessage()
        for record in caplog.records
        if "preview_image_chars≈" in record.getMessage()
    ]
    assert logged, "expected preview_image_chars log line"
    match = re.search(r"preview_image_chars≈(\d+)", logged[-1])
    assert match, logged[-1]
    assert int(match.group(1)) > 0
    assert int(match.group(1)) == direct_count
