VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT = """
You are verifying and correcting extracted fields for an outside-scholarship check.

You are given a first-pass candidate from Azure Document Intelligence:
{di_candidate_json}

{check_images_description}

Instructions:
- Verify every field against the images.
- Correct any wrong first-pass values.
- Extract all student IDs as `pid_list`. A PID is exactly 10 digits. Include every 10-digit PID visible on any provided image. A check may have multiple PIDs. Do not include approval numbers, check numbers, or any other value that is not exactly 10 digits.
- Return `amount` as a numeric string when possible (for example "1250.00").
- `provider` means payer/remitter/check issuer.
- `scholarship_name` can be null when absent.

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

# Backward-compatible exports for modules that still import these names.
CLASSIFY_CHECK_PROMPT = "Deprecated for outside scholarship hybrid flow."
EXTRACT_CHECK_FIELDS_PROMPT = VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT
