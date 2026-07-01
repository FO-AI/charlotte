import operator
from typing import Annotated, Dict, List, Optional, TypedDict


class CheckPair(TypedDict):
    check_index: int
    front_image: bytes
    back_image: bytes
    pair_pdf_bytes: bytes


class OrchestratorState(TypedDict):
    pdf_folder: Optional[str]           # folder path for disk-based processing
    pdf_files_bytes: List[bytes]        # raw PDF bytes for upload-based processing
    check_pairs: List[CheckPair]        # paired front/back check pages
    check_results: Annotated[           # fan-in: workers append here via operator.add
        list, operator.add
    ]
    final_payload: Dict                 # aggregated output handed back to the route


class WorkerState(TypedDict):
    check_index: int
    front_image: bytes
    back_image: bytes
    pair_pdf_bytes: bytes
    di_candidate: Dict
    llm_candidate: Dict
