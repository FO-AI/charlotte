VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT = """
You are verifying and correcting extracted fields for an outside-scholarship check.

You are given a first-pass candidate from Azure Document Intelligence:
{di_candidate_json}

You will receive two images:
1) Front of the check
2) Back of the check

Instructions:
- Verify every field against the images.
- Correct any wrong first-pass values.
- Extract all student IDs as `pid_list` (include every PID visible on either side).
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

# Backward-compatible exports for modules that still import these names.
CLASSIFY_CHECK_PROMPT = "Deprecated for outside scholarship hybrid flow."
EXTRACT_CHECK_FIELDS_PROMPT = VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT
