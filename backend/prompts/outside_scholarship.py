EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT = """
You are reading the fields of one scanned outside-scholarship check and, when present, the supporting
pages that follow it.

{check_images_description}

Instructions:
- Read every value directly from the images. Return null for a field you cannot read clearly; never guess.
- `pid_list`, `amount`, and `check_number` come only from the check front and, when one was scanned, the
  check back. A supporting page that repeats them, shows a different dollar amount, or shows an extra PID
  does not change those three fields. Do not add a PID that appears only on a supporting page. A PID is a
  UNC student ID of exactly 9 digits (for example 730123456). It often appears on the back, in the memo
  line, or next to "PID", and a check can list several. Do not include the routing or account number from
  the MICR line along the bottom of the check (the routing number is also 9 digits), the check number,
  approval or authorization numbers, or any other number that is not a student PID.
- `amount`: the check amount as a numeric string (for example "1250.00").
- `pid_amounts`: per-student shares from supporting pages only. Return a list of objects such as
  {"pid": "730123456", "amount": "1000.00"} only when a supporting page clearly designates that
  PID's individual dollar amount. Include only PIDs that already appear in `pid_list`; do not add a
  PID that appears only on a supporting page. If supporting pages do not clearly assign every check
  PID an amount, return only the clearly designated PID/amount pairs, or an empty list. Never invent
  equal shares from boilerplate language such as "if not indicated, we will split evenly".
- `check_number`: the check number printed on the check.
- `name`: the student the scholarship is for. Use the student's name on the check when the check names
  one (memo, a "student" or "for" line, or "FBO"). These checks are often payable to the university. When
  the check is payable to the university and does not name the student, use the student name on a
  supporting page. Return the student's name, never the university's. If the payee line names both (for
  example "UNC-CH FBO Jane Doe"), return only the student. Return null when no student is named.
- `provider`: the check issuer, payer, or remitter. Use a supporting page only when the check itself does
  not name an issuer.
- `scholarship_name`: the scholarship or award program. Use the name on the check when the check names
  the program. Otherwise use the program name on a supporting page. Return null when neither names a
  program. A blank scholarship name is acceptable.
- `aid_term`: the term this award applies to, or null. Use the term on the check when the check states
  one (for example "FALL 2026" on the face). Otherwise use a supporting page, and only a marked checkbox
  or a sentence that applies this award to a term. The printed list of options is not a selection. A line
  such as "if not indicated, we will split evenly" is not a selection. When one supporting page applies
  the award to a term (a voucher code such as "grad/fall-spring", or a letter that says the award is for
  Fall and Spring), use that term even if another page's title names only one season. Map the wording to
  exactly one of these codes, and return null for anything else:
  Fall -> "F"
  Spring -> "S"
  Fall and Spring, including "grad/fall-spring" and "Fall 2026 and Spring 2027" -> "F/S"
  Summer Session 1 -> "SS1"
  Summer Session 2 -> "SS2"
  Do not derive an aid year from a date or from "2026-2027" on a page.

Return ONLY valid JSON with exactly these keys:
{
  "pid_list": ["string", "..."],
  "pid_amounts": [{"pid": "string", "amount": "string"}, "..."],
  "amount": "string or null",
  "check_number": "string or null",
  "name": "string or null",
  "provider": "string or null",
  "scholarship_name": "string or null",
  "aid_term": "F, S, F/S, SS1, SS2, or null"
}
"""


def describe_check_images(has_back: bool, supporting_count: int) -> str:
    """Tell the model which image is the check and which images are supporting pages."""
    lines = ["Image 1 is the front of the check."]
    next_index = 2
    if has_back:
        lines.append(f"Image {next_index} is the back of the check.")
        next_index += 1
    else:
        lines.append(
            "No back was scanned for this check. Do not invent values that would only appear on the back."
        )
    if supporting_count == 1:
        lines.append(
            f"Image {next_index} is a supporting document for this check "
            "(a letter, a form, a voucher, or a remittance stub). It is not the check."
        )
    elif supporting_count > 1:
        last_index = next_index + supporting_count - 1
        lines.append(
            f"Images {next_index} through {last_index} are supporting documents for this check "
            "(letters, forms, vouchers, or remittance stubs). They are not the check."
        )
    else:
        lines.append("This check has no supporting documents.")
    return "\n".join(lines)


CLASSIFY_CHECK_SIDES_PROMPT = """
You are sorting scanned pages from one PDF of outside-scholarship checks.

Each image below is preceded by its page number. Label every page as one of:
- "front": the face of a check. A front has a payee line, a MICR line along the bottom, or a signature.
- "back": the reverse of a check (endorsement area, deposit stamps, handwritten notes, or a blank reverse).
- "supporting": a letter, a form, a voucher, or a remittance stub that belongs with a check. A page that
  shows an amount and a student PID but has no check face (no payee line, no MICR line, and no signature)
  is "supporting", not "front".

Use the page number from each image's label, even when it does not start at 1.
Return ONLY valid JSON with one entry per labeled page, in page order, for example:
{
  "pages": [
    {"page": 11, "side": "front"},
    {"page": 12, "side": "supporting"}
  ]
}
"""
