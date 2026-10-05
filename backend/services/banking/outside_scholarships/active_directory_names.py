"""Active Directory (Entra ID) names for extracted PIDs, shown beside the check's payee name.

UNC stores a student's PID as the Entra ID `employeeId`, so each PID is looked up there.
"""

from typing import Any, Dict, List, Literal, Optional, Sequence, TypedDict

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


def _distinct_pids_from_checks(checks: Sequence[Dict[str, Any]]) -> List[str]:
    pids = (_normalize_pid(pid) for check in checks for pid in check.get("pid_list") or [])
    return list(dict.fromkeys(pid for pid in pids if pid))


def _normalize_pid_list(pids: Sequence[Any]) -> List[str]:
    return list(dict.fromkeys(_normalize_pid(pid) for pid in pids if _normalize_pid(pid)))


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
