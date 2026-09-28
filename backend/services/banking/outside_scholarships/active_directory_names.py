"""Active Directory (Entra ID) names for extracted PIDs, shown beside the check's payee name.

UNC stores a student's PID as the Entra ID `employeeId`, so each PID is looked up there.
"""

from typing import Any, Dict, List, Sequence

from config import get_logger
from services.azure_services import DirectoryLookupError, DirectoryUser, GraphUserDirectory

logger = get_logger(__name__)

LOOKUP_FAILED = "Lookup failed"
_NAME_SEPARATOR = "; "


def format_active_directory_name(users: Sequence[DirectoryUser]) -> str:
    """"Surname, GivenName" per account, else its display name; distinct names are joined.

    Several accounts can share one PID. Showing every distinct name lets a reviewer
    notice instead of the workbook silently picking one.
    """
    names = (_last_first_name(user) for user in users)
    return _NAME_SEPARATOR.join(dict.fromkeys(name for name in names if name))


def _last_first_name(user: DirectoryUser) -> str:
    if user.surname and user.given_name:
        return f"{user.surname}, {user.given_name}"
    return user.display_name or ""


def _distinct_pids(checks: Sequence[Dict[str, Any]]) -> List[str]:
    pids = (str(pid).strip() for check in checks for pid in check.get("pid_list") or [])
    return list(dict.fromkeys(pid for pid in pids if pid))


async def lookup_active_directory_names(
    directory: GraphUserDirectory,
    checks: Sequence[Dict[str, Any]],
    access_token: str,
) -> Dict[str, str]:
    """Map each extracted PID to its Active Directory name.

    PIDs with no directory match are left out, so their cell stays blank. If Graph
    fails, the error is logged and every PID maps to LOOKUP_FAILED: the extraction
    work is still returned, and the column says the names are missing, not unknown.
    """
    pids = _distinct_pids(checks)
    if not pids:
        return {}

    try:
        users_by_pid = await directory.find_users_by_employee_id(pids, access_token)
    except DirectoryLookupError:
        logger.exception("outside_scholarships.active_directory_names: lookup failed for %s PIDs", len(pids))
        return {pid: LOOKUP_FAILED for pid in pids}

    return {pid: format_active_directory_name(users) for pid, users in users_by_pid.items()}
