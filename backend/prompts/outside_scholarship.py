EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT = """
You are reading the fields of one scanned outside-scholarship check.

{check_images_description}

Instructions:
- Read every value directly from the images. Return null for a field you cannot read clearly; never guess.
- `pid_list`: every student PID written or printed on any image, each as its own entry. A PID is a
  UNC student ID of exactly 9 digits (for example 730123456). It often appears on the back, in the
  memo line, or next to "PID", and a check can list several. Do not include the routing or account
  number from the MICR line along the bottom of the check (the routing number is also 9 digits), the
  check number, approval or authorization numbers, or any other number that is not a student PID.
- `amount`: the check amount as a numeric string (for example "1250.00").
- `check_number`: the check number printed on the check.
- `name`: the student the scholarship is for. These checks are usually made payable to the
  university, so the student's name is often in the memo line, a "student" or "for" line, or a
  note; return the student's name, never the university's. If the payee line names both (for
  example "UNC-CH FBO Jane Doe"), return only the student. Return null when no student is named.
- `provider`: the payer, remitter, or check issuer.
- `scholarship_name`: the scholarship or award the check names, or null when absent.

Return ONLY valid JSON with exactly these keys:
{
  "pid_list": ["string", "..."],
  "amount": "string or null",
  "check_number": "string or null",
  "name": "string or null",
  "provider": "string or null",
  "scholarship_name": "string or null"
}
"""

CHECK_IMAGES_FRONT_AND_BACK = """You will receive two images:
1) Front of the check
2) Back of the check"""

CHECK_IMAGES_FRONT_ONLY = """You will receive one image: the front of the check.
No back was scanned for this check, so do not invent values that would only appear on the back."""

CLASSIFY_CHECK_SIDES_PROMPT = """
You are sorting scanned pages from a PDF of outside-scholarship checks.

Each image below is preceded by its page number. Label every page as one of:
- "front": the face of a check (payee line, written or printed amount, MICR line, signature).
- "back": the reverse of a check (endorsement area, deposit stamps, handwritten notes, or blank).

Use the page number from each image's label, even when it does not start at 1.
Return ONLY valid JSON with one entry per labeled page, in page order, for example:
{
  "pages": [
    {"page": 11, "side": "front"},
    {"page": 12, "side": "back"}
  ]
}
"""
