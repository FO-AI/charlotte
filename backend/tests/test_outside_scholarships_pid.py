"""A PID is 10 digits. Approval numbers must not become extra export rows."""

from services.banking.outside_scholarships.nodes import _dedupe_pids, _normalize_pid
from services.data_loaders.outside_scholarships_json_to_excel import OutsideScholarshipsDataLoader

_PID = "1234567890"
_APPROVAL_NUMBER = "1380307"


def test_normalize_pid_keeps_exactly_ten_digits():
    assert _normalize_pid(_PID) == _PID
    assert _normalize_pid(f"P{_PID}") == _PID
    assert _normalize_pid("123-456-7890") == _PID
    assert _normalize_pid(_APPROVAL_NUMBER) is None
    assert _normalize_pid("123456789") is None
    assert _normalize_pid("12345678901") is None


def test_dedupe_pids_drops_approval_number_beside_pid():
    assert _dedupe_pids([_PID, _APPROVAL_NUMBER, _PID]) == [_PID]


def test_excel_emits_one_row_when_check_has_pid_and_approval_number():
    loader = OutsideScholarshipsDataLoader(aid_year="2026", aid_term="F")
    rows = loader._expand_rows(
        [
            {
                "pid_list": [_PID, _APPROVAL_NUMBER],
                "amount": "1000.00",
                "name": "",
                "provider": "Cabinetworks Group Michigan, LLC",
                "scholarship_name": "",
            }
        ]
    )

    assert len(rows) == 1
    assert rows[0][0] == _PID
    assert rows[0][1] == 1000.0
    assert rows[0][5] == "Cabinetworks Group Michigan, LLC"


def test_excel_keeps_multiple_ten_digit_pids_and_blank_when_none():
    loader = OutsideScholarshipsDataLoader(aid_year="2026", aid_term="F")
    rows = loader._expand_rows(
        [
            {
                "pid_list": ["1234567890", "0987654321"],
                "amount": "50.00",
            },
            {
                "pid_list": [_APPROVAL_NUMBER],
                "amount": "25.00",
            },
        ]
    )

    assert [row[0] for row in rows] == ["1234567890", "0987654321", ""]
