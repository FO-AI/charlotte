from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from openpyxl import Workbook
from openpyxl.styles import Font


def _active_directory_display_name(result: Optional[Mapping[str, Any]]) -> str:
    # Lazy import: module-level import of services.banking circularizes via data_loaders.
    from services.banking.outside_scholarships.active_directory_names import (
        active_directory_display_name,
    )

    return active_directory_display_name(result)  # type: ignore[arg-type]


class OutsideScholarshipsDataLoader:
    """Build an Excel workbook from outside-scholarship extraction or review output."""

    HEADERS = [
        "PID",
        "Amount",
        "Name",
        "Active Directory Name",
        "Aid year",
        "Aid term",
        "Provider",
        "Scholarship name",
    ]

    REVIEW_HEADERS = HEADERS + [
        "Edited",
        "Verified",
        "Extracted values",
    ]

    def __init__(
        self,
        aid_year: Optional[str] = None,
        aid_term: Optional[str] = None,
        active_directory_names: Optional[Mapping[str, str]] = None,
        reviewed_by: Optional[str] = None,
    ):
        self.aid_year = self._normalize_aid_year(aid_year)
        self.aid_term = self._normalize_aid_term(aid_term)
        self.active_directory_names = active_directory_names or {}
        self.reviewed_by = (reviewed_by or "").strip()
        self.report_date = date.today()

    @staticmethod
    def _normalize_aid_year(aid_year: Optional[str]) -> str:
        value = str(aid_year).strip() if aid_year is not None else ""
        if not value:
            return str(date.today().year)
        if not value.isdigit() or len(value) != 4:
            raise ValueError("Aid year must be a 4-digit year (for example: 2026).")
        return value

    @staticmethod
    def _normalize_aid_term(aid_term: Optional[str]) -> str:
        value = (aid_term or "F").strip().upper()
        if value not in {"F", "S"}:
            raise ValueError("Aid term must be 'F' or 'S'.")
        return value

    @staticmethod
    def _to_decimal_amount(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")

        text = str(value).strip()
        if not text:
            return Decimal("0")

        cleaned = text.replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _expand_rows(self, checks: List[Dict[str, Any]]) -> List[List[Any]]:
        """Legacy path: extraction payload with pid_list + flat AD name map."""
        rows: List[List[Any]] = []

        for check in checks:
            amount_decimal = self._to_decimal_amount(check.get("amount"))
            amount_value = float(amount_decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

            name = check.get("name") or ""
            provider = check.get("provider") or ""
            scholarship_name = check.get("scholarship_name") or ""

            pid_list = check.get("pid_list")
            if not isinstance(pid_list, list) or not pid_list:
                pid_list = [""]

            for pid in pid_list:
                pid_text = str(pid).strip() if pid is not None else ""
                rows.append(
                    [
                        pid_text,
                        amount_value,
                        name,
                        self.active_directory_names.get(pid_text, ""),
                        self.aid_year,
                        self.aid_term,
                        provider,
                        scholarship_name,
                    ]
                )

        return rows

    @staticmethod
    def _pid_entries(check: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
        raw = check.get(key)
        if not isinstance(raw, list):
            return []
        entries = []
        for item in raw:
            if isinstance(item, dict):
                entries.append(item)
            elif item is not None and str(item).strip():
                entries.append({"pid": str(item).strip()})
        return entries

    @classmethod
    def _audit_diff(
        cls,
        extracted: Dict[str, Any],
        reviewed: Dict[str, Any],
        extracted_pids: Sequence[str],
        reviewed_pids: Sequence[str],
    ) -> Tuple[bool, str]:
        changes: List[str] = []
        field_labels = (
            ("amount", "Amount"),
            ("name", "Name"),
            ("check_number", "Check number"),
            ("provider", "Provider"),
            ("scholarship_name", "Scholarship name"),
        )
        for field, label in field_labels:
            extracted_value = cls._text(extracted.get(field))
            reviewed_value = cls._text(reviewed.get(field))
            if extracted_value != reviewed_value:
                changes.append(f"{label}: {extracted_value or '(blank)'}")

        extracted_set = [pid for pid in extracted_pids if pid]
        reviewed_set = [pid for pid in reviewed_pids if pid]
        for pid in reviewed_set:
            if pid not in extracted_set:
                changes.append(f"Added PID: {pid}")
        for pid in extracted_set:
            if pid not in reviewed_set:
                changes.append(f"Removed PID: {pid}")

        edited = bool(changes)
        return edited, "; ".join(changes)

    def _expand_reviewed_rows(self, checks: List[Dict[str, Any]]) -> List[List[Any]]:
        rows: List[List[Any]] = []

        for check in checks:
            extracted = check.get("extracted") if isinstance(check.get("extracted"), dict) else {}
            reviewed = check.get("reviewed") if isinstance(check.get("reviewed"), dict) else check
            verified = bool(check.get("verified"))

            amount_decimal = self._to_decimal_amount(reviewed.get("amount"))
            amount_value = float(amount_decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
            name = reviewed.get("name") or ""
            provider = reviewed.get("provider") or ""
            scholarship_name = reviewed.get("scholarship_name") or ""

            reviewed_pid_entries = self._pid_entries(reviewed, "pids")
            if not reviewed_pid_entries:
                # Fall back to pid_list shape if present.
                raw_list = reviewed.get("pid_list")
                if isinstance(raw_list, list) and raw_list:
                    reviewed_pid_entries = [{"pid": pid} for pid in raw_list]
                else:
                    reviewed_pid_entries = [{"pid": ""}]

            extracted_pid_entries = self._pid_entries(extracted, "pids")
            if not extracted_pid_entries:
                raw_list = extracted.get("pid_list")
                if isinstance(raw_list, list):
                    extracted_pid_entries = [{"pid": pid} for pid in raw_list]

            extracted_pids = [self._text(entry.get("pid")) for entry in extracted_pid_entries]
            reviewed_pids = [self._text(entry.get("pid")) for entry in reviewed_pid_entries]

            edited, extracted_values = self._audit_diff(extracted, reviewed, extracted_pids, reviewed_pids)

            for entry in reviewed_pid_entries:
                pid_text = self._text(entry.get("pid"))
                ad = entry.get("active_directory") if isinstance(entry.get("active_directory"), dict) else None
                ad_name = (
                    _active_directory_display_name(ad)
                    if ad is not None
                    else self.active_directory_names.get(pid_text, "")
                )
                row_edited = edited
                # An added PID alone marks the row edited (already in extracted_values).
                if pid_text and pid_text not in extracted_pids:
                    row_edited = True
                rows.append(
                    [
                        pid_text,
                        amount_value,
                        name,
                        ad_name,
                        self.aid_year,
                        self.aid_term,
                        provider,
                        scholarship_name,
                        "Yes" if row_edited else "",
                        "Yes" if verified else "",
                        extracted_values if row_edited else "",
                    ]
                )

        return rows

    def build_excel_bytes(self, extraction_payload: Dict[str, Any]) -> BytesIO:
        checks_raw = extraction_payload.get("checks") if isinstance(extraction_payload, dict) else []
        checks = [check for check in checks_raw if isinstance(check, dict)] if isinstance(checks_raw, list) else []
        rows = self._expand_rows(checks)
        return self._write_workbook(checks, rows, headers=self.HEADERS, include_reviewed_by=False)

    def build_reviewed_excel_bytes(self, review_payload: Dict[str, Any]) -> BytesIO:
        checks_raw = review_payload.get("checks") if isinstance(review_payload, dict) else []
        checks = [check for check in checks_raw if isinstance(check, dict)] if isinstance(checks_raw, list) else []
        rows = self._expand_reviewed_rows(checks)
        return self._write_workbook(checks, rows, headers=self.REVIEW_HEADERS, include_reviewed_by=True)

    def _write_workbook(
        self,
        checks: List[Dict[str, Any]],
        rows: List[List[Any]],
        headers: Sequence[str],
        include_reviewed_by: bool,
    ) -> BytesIO:
        total_amount = Decimal("0")
        for check in checks:
            reviewed = check.get("reviewed") if isinstance(check.get("reviewed"), dict) else check
            total_amount += self._to_decimal_amount(reviewed.get("amount"))

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "outside_scholarships"

        worksheet["A1"] = "Total amount"
        worksheet["B1"] = float(total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        worksheet["A2"] = "Check count"
        worksheet["B2"] = len(checks)
        worksheet["A3"] = "Date"
        worksheet["B3"] = self.report_date.isoformat()

        worksheet["A1"].font = Font(bold=True)
        worksheet["A2"].font = Font(bold=True)
        worksheet["A3"].font = Font(bold=True)
        worksheet["B1"].number_format = "$#,##0.00"

        if include_reviewed_by:
            worksheet["A4"] = "Reviewed by"
            worksheet["B4"] = self.reviewed_by
            worksheet["A4"].font = Font(bold=True)
            header_row_index = 6
            freeze_pane = "A7"
        else:
            header_row_index = 5
            freeze_pane = "A6"

        for column_index, header in enumerate(headers, start=1):
            cell = worksheet.cell(row=header_row_index, column=column_index, value=header)
            cell.font = Font(bold=True)

        for row_offset, row_values in enumerate(rows, start=1):
            for column_index, value in enumerate(row_values, start=1):
                worksheet.cell(row=header_row_index + row_offset, column=column_index, value=value)

        worksheet.freeze_panes = freeze_pane

        column_widths = {
            "A": 18,
            "B": 12,
            "C": 26,
            "D": 26,
            "E": 12,
            "F": 10,
            "G": 26,
            "H": 30,
            "I": 10,
            "J": 10,
            "K": 40,
        }
        for column_name, width in column_widths.items():
            worksheet.column_dimensions[column_name].width = width

        first_data_row = header_row_index + 1
        last_data_row = first_data_row + max(len(rows) - 1, 0)
        for row_index in range(first_data_row, last_data_row + 1):
            worksheet.cell(row=row_index, column=2).number_format = "$#,##0.00"

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output
