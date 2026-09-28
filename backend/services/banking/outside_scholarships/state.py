import operator
from typing import Annotated, Dict, List, Optional, TypedDict


class CheckPair(TypedDict):
    check_index: int
    front_image: bytes
    back_image: Optional[bytes]         # None when no back was scanned for the check
    pair_pdf_bytes: bytes


class OrchestratorState(TypedDict):
    pdf_folder: Optional[str]           # folder path for disk-based processing
    pdf_files_bytes: List[bytes]        # raw PDF bytes for upload-based processing
    check_pairs: List[CheckPair]        # pages grouped per check: front + optional back
    check_results: Annotated[           # fan-in: workers append here via operator.add
        list, operator.add
    ]
    final_payload: Dict                 # aggregated output handed back to the route


class WorkerState(TypedDict):
    check_index: int
    front_image: bytes
    back_image: Optional[bytes]         # None when no back was scanned for the check
    pair_pdf_bytes: bytes
