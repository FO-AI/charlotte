import operator
from typing import Annotated, Dict, List, Optional, TypedDict


class CheckPair(TypedDict):
    check_index: int
    pair_pdf_bytes: bytes               # the check's front page, then its back when one was scanned
    front_page: int                     # 1-based PDF page number of the front
    back_page: Optional[int]            # 1-based PDF page number of the back, or None


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
    pair_pdf_bytes: bytes               # the check's front page, then its back when one was scanned
    front_page: int
    back_page: Optional[int]
