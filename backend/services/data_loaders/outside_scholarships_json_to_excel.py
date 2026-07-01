from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font


class OutsideScholarshipsDataLoader:
    """Build an Excel workbook from outside-scholarship extraction output."""

    HEADERS = [
        "PID",
        "Amount",
        "Name",
        "Aid year",
        "Aid term",
        "Provider",
        "Scholarship name",
    ]

    def __init__(self, aid_year: Optional[str] = None, aid_term: Optional[str] = None):
        self.aid_year = self._normalize_aid_year(aid_year)
        self.aid_term = self._normalize_aid_term(aid_term)
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

    def _expand_rows(self, checks: List[Dict[str, Any]]) -> List[List[Any]]:
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
                rows.append(
                    [
                        str(pid).strip() if pid is not None else "",
                        amount_value,
                        name,
                        self.aid_year,
                        self.aid_term,
                        provider,
                        scholarship_name,
                    ]
                )

        return rows

    def build_excel_bytes(self, extraction_payload: Dict[str, Any]) -> BytesIO:
        checks_raw = extraction_payload.get("checks") if isinstance(extraction_payload, dict) else []
        checks = [check for check in checks_raw if isinstance(check, dict)] if isinstance(checks_raw, list) else []
        rows = self._expand_rows(checks)

        total_amount = Decimal("0")
        for check in checks:
            total_amount += self._to_decimal_amount(check.get("amount"))

        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "outside_scholarships"

        # Summary block at the top.
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

        header_row_index = 5
        for column_index, header in enumerate(self.HEADERS, start=1):
            cell = worksheet.cell(row=header_row_index, column=column_index, value=header)
            cell.font = Font(bold=True)

        for row_offset, row_values in enumerate(rows, start=1):
            for column_index, value in enumerate(row_values, start=1):
                worksheet.cell(row=header_row_index + row_offset, column=column_index, value=value)

        # Keep headers visible while scrolling rows.
        worksheet.freeze_panes = "A6"

        # Minimal width tuning for readability.
        column_widths = {
            "A": 18,
            "B": 12,
            "C": 26,
            "D": 12,
            "E": 10,
            "F": 26,
            "G": 30,
        }
        for column_name, width in column_widths.items():
            worksheet.column_dimensions[column_name].width = width

        # Amount formatting for row items.
        first_data_row = header_row_index + 1
        last_data_row = first_data_row + max(len(rows) - 1, 0)
        for row_index in range(first_data_row, last_data_row + 1):
            worksheet.cell(row=row_index, column=2).number_format = "$#,##0.00"

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return output
