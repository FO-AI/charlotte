"""Microsoft Graph user directory: find Entra ID users by their employeeId.

Calls are delegated: they carry the signed-in user's own Graph access token (the app
registration holds the delegated User.Read.All permission), so results are limited to
what that user may read in the directory.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import httpx

GRAPH_USERS_URL = "https://graph.microsoft.com/v1.0/users"
# Graph rejects filters with more than 15 child clauses; each value in an `in` list counts as one.
GRAPH_FILTER_MAX_VALUES = 15
GRAPH_TIMEOUT_SECONDS = 15.0
_SELECTED_PROPERTIES = "employeeId,givenName,surname,displayName"
_NO_ERROR_CODE = "no Graph error code"


class DirectoryLookupError(Exception):
    """Microsoft Graph could not be reached or refused the lookup."""


@dataclass(frozen=True)
class DirectoryUser:
    employee_id: str
    given_name: Optional[str]
    surname: Optional[str]
    display_name: Optional[str]


class GraphUserDirectory:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        # None uses httpx's network transport; tests pass an httpx.MockTransport.
        self._transport = transport

    async def find_users_by_employee_id(
        self, employee_ids: Sequence[str], access_token: str
    ) -> Dict[str, DirectoryUser]:
        """Map each requested employee ID to its user; IDs with no user are absent.

        Raises DirectoryLookupError when any Graph request fails.
        """
        user_by_employee_id: Dict[str, DirectoryUser] = {}
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(
            transport=self._transport, headers=headers, timeout=GRAPH_TIMEOUT_SECONDS
        ) as client:
            for start in range(0, len(employee_ids), GRAPH_FILTER_MAX_VALUES):
                batch = employee_ids[start : start + GRAPH_FILTER_MAX_VALUES]
                # Graph compares employeeId case-insensitively; key results by the ID as requested.
                requested_by_folded_id = {employee_id.casefold(): employee_id for employee_id in batch}
                for user in await self._fetch_users(client, batch):
                    requested_id = requested_by_folded_id[user.employee_id.casefold()]
                    user_by_employee_id[requested_id] = user
        return user_by_employee_id

    @staticmethod
    async def _fetch_users(client: httpx.AsyncClient, employee_ids: Sequence[str]) -> List[DirectoryUser]:
        params = {"$filter": _employee_id_filter(employee_ids), "$select": _SELECTED_PROPERTIES}
        try:
            response = await client.get(GRAPH_USERS_URL, params=params)
        except httpx.HTTPError as exc:
            raise DirectoryLookupError(f"Microsoft Graph request failed: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise DirectoryLookupError(
                f"Microsoft Graph returned {response.status_code} ({_graph_error_code(response)})"
            )
        return [_to_directory_user(record) for record in response.json()["value"]]


def _employee_id_filter(employee_ids: Sequence[str]) -> str:
    # OData string literals escape a single quote by doubling it.
    quoted_ids = ",".join("'" + employee_id.replace("'", "''") + "'" for employee_id in employee_ids)
    return f"employeeId in ({quoted_ids})"


def _graph_error_code(response: httpx.Response) -> str:
    try:
        return response.json().get("error", {}).get("code", _NO_ERROR_CODE)
    except ValueError:
        return _NO_ERROR_CODE


def _to_directory_user(record: Dict) -> DirectoryUser:
    return DirectoryUser(
        employee_id=record["employeeId"],
        given_name=record.get("givenName"),
        surname=record.get("surname"),
        display_name=record.get("displayName"),
    )
