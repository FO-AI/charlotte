"""Active Directory (Entra ID) names for extracted PIDs, shown beside the check's payee name.

UNC stores a student's PID as the Entra ID `employeeId`, so each PID is looked up there.
"""

from typing import Any, Dict, List, Literal, Optional, Sequence, TypedDict

import re

from config import get_logger
from services.azure_services import DirectoryLookupError, DirectoryUser, GraphUserDirectory

logger = get_logger(__name__)

AdStatus = Literal["found", "not_found", "lookup_failed"]

# Keep in sync with nodes._PID_DIGIT_COUNT and the review UI PID_DIGIT_COUNT.
_PID_DIGIT_COUNT = 9


class ActiveDirectoryResult(TypedDict):
    status: AdStatus
    name: Optional[str]


LOOKUP_FAILED_LABEL = "Lookup failed"


def format_active_directory_name(user: DirectoryUser) -> str:
    """"Surname, GivenName", or the display name when either part is missing."""
    if user.surname and user.given_name:
        return f"{user.surname}, {user.given_name}"
    return user.display_name or ""


def _normalize_pid(pid: Any) -> str:
    """Nine-digit employeeId form, or empty when not a student PID (e.g. approval numbers)."""
    digits = "".join(ch for ch in str(pid or "") if ch.isdigit())
    return digits if len(digits) == _PID_DIGIT_COUNT else ""


def _pids_from_value(pid: Any) -> List[str]:
    """Nine-digit PIDs in one value, including when an approval number shares the string."""
    text = str(pid or "").strip()
    if not text:
        return []
    whole = _normalize_pid(text)
    if whole:
        return [whole]

    found: List[str] = []
    seen = set()
    for token in re.split(r"[\s,;/|]+", text):
        normalized = _normalize_pid(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        found.append(normalized)
    if found:
        return found

    for match in re.finditer(rf"(?<!\d)\d{{{_PID_DIGIT_COUNT}}}(?!\d)", text):
        normalized = match.group(0)
        if normalized not in seen:
            seen.add(normalized)
            found.append(normalized)
    return found


def _distinct_pids_from_checks(checks: Sequence[Dict[str, Any]]) -> List[str]:
    pids = (
        normalized
        for check in checks
        for pid in check.get("pid_list") or []
        for normalized in _pids_from_value(pid)
    )
    return list(dict.fromkeys(pids))


def _normalize_pid_list(pids: Sequence[Any]) -> List[str]:
    return list(dict.fromkeys(pid for value in pids for pid in _pids_from_value(value)))


async def lookup_pids(
    directory: GraphUserDirectory,
    pids: Sequence[Any],
    access_token: str,
) -> Dict[str, ActiveDirectoryResult]:
    """Map each PID to an Active Directory status and display name.

    Graph failure maps every requested PID to lookup_failed so the review UI can
    still show extraction results with a Retry action.
    """
    normalized = _normalize_pid_list(pids)
    if not normalized:
        return {}

    try:
        user_by_pid = await directory.find_users_by_employee_id(normalized, access_token)
    except DirectoryLookupError:
        logger.exception("outside_scholarships.active_directory_names: lookup failed for %s PIDs", len(normalized))
        return {pid: {"status": "lookup_failed", "name": None} for pid in normalized}

    results: Dict[str, ActiveDirectoryResult] = {}
    for pid in normalized:
        user = user_by_pid.get(pid)
        if user is None:
            results[pid] = {"status": "not_found", "name": None}
        else:
            results[pid] = {"status": "found", "name": format_active_directory_name(user)}
    return results


async def lookup_active_directory_names(
    directory: GraphUserDirectory,
    checks: Sequence[Dict[str, Any]],
    access_token: str,
) -> Dict[str, ActiveDirectoryResult]:
    """Look up every distinct PID found on the extracted checks."""
    return await lookup_pids(directory, _distinct_pids_from_checks(checks), access_token)


def active_directory_display_name(result: Optional[ActiveDirectoryResult]) -> str:
    """Excel cell text for an Active Directory lookup result."""
    if not result:
        return ""
    if result["status"] == "found":
        return result.get("name") or ""
    if result["status"] == "lookup_failed":
        return LOOKUP_FAILED_LABEL
    return ""
