import base64
import json
import math
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
from langgraph.types import RunnableConfig, Send

from config import get_logger
from prompts.outside_scholarship import (
    CHECK_IMAGES_FRONT_AND_BACK,
    CHECK_IMAGES_FRONT_ONLY,
    CLASSIFY_CHECK_SIDES_PROMPT,
    EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT,
)
from services.banking.outside_scholarships.state import CheckPair, OrchestratorState, WorkerState

logger = get_logger(__name__)
_MODEL = "gpt-5-chat"

_FRONT_SIDE = "front"
_BACK_SIDE = "back"
_PAGE_SIDES = {_FRONT_SIDE, _BACK_SIDE}
_PAGE_RENDER_DPI = 200
# Thumbnails are enough to tell a check's face from its reverse and keep requests small.
_SIDE_CLASSIFICATION_DPI = 50
# Conservative, to stay under the per-request image limit of vision chat models.
_SIDE_CLASSIFICATION_BATCH_SIZE = 10
# The model sometimes leaves a page out of a batch's reply (3 of 7 real runs on 2026-09-28), and
# that fails the whole upload. A batch is cheap to resend and usually comes back complete.
_SIDE_CLASSIFICATION_ATTEMPTS = 3

# PyMuPDF does not support use from several threads at once, and check workers (and concurrent
# uploads) run in parallel threads. Every PyMuPDF call, including opening and closing documents,
# holds this lock. Hold it only around PyMuPDF work, never across an LLM call.
PYMUPDF_LOCK = threading.Lock()

_EMPTY_MARKERS = {"", "null", "none", "n/a", "na", "unknown", "not found", "not provided"}

# A UNC student PID is exactly nine digits. Anything else the model lists, such as an approval
# or check number, is not a PID and must not reach the export or the directory lookup.
_PID_DIGIT_COUNT = 9


def _clean_optional(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() in _EMPTY_MARKERS:
        return None
    return text


def _normalize_amount(value: Any) -> Optional[str]:
    raw = _clean_optional(value)
    if raw is None:
        return None

    cleaned = raw.replace("$", "").replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", cleaned):
        return raw

    if "." not in cleaned:
        return f"{cleaned}.00"

    dollars, cents = cleaned.split(".", 1)
    cents = cents[:2].ljust(2, "0")
    return f"{dollars}.{cents}"


def _normalize_pid(value: Any) -> Optional[str]:
    """The PID's digits, without separators or a prefix, or None when it is not a nine-digit PID."""
    raw = _clean_optional(value)
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return digits if len(digits) == _PID_DIGIT_COUNT else None


def _dedupe_pids(pid_values: Sequence[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()

    for value in pid_values:
        pid = _normalize_pid(value)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        normalized.append(pid)

    return normalized


def _normalize_text(value: Any) -> Optional[str]:
    raw = _clean_optional(value)
    if raw is None:
        return None
    return re.sub(r"\s+", " ", raw).strip()


def _pid_candidates(fields: Dict[str, Any]) -> Sequence[Any]:
    raw_pids = fields.get("pid_list")
    if isinstance(raw_pids, str):
        return re.split(r"[\n,;/]+", raw_pids)
    if isinstance(raw_pids, list):
        return raw_pids
    if raw_pids is None:
        return []
    # A single PID sometimes comes back as a bare JSON number instead of a list.
    return [raw_pids]


def _normalize_check_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pid_list": _dedupe_pids(_pid_candidates(fields)),
        "amount": _normalize_amount(fields.get("amount")),
        "check_number": _normalize_text(fields.get("check_number")),
        "name": _normalize_text(fields.get("name")),
        "provider": _normalize_text(fields.get("provider")),
        "scholarship_name": _normalize_text(fields.get("scholarship_name")),
    }


def _render_page_png(document: fitz.Document, page_index: int, dpi: int) -> bytes:
    scale = dpi / 72
    return document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png")


def _png_image_part(png_bytes: bytes) -> Dict[str, Any]:
    encoded = base64.b64encode(png_bytes).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}


def _parse_page_sides(reply: str, page_numbers: Sequence[int]) -> List[str]:
    """Validate a side-classification reply and return the sides in page order.

    Raises RuntimeError, not ValueError, for a bad reply: it is a model failure rather than a
    problem with the uploaded PDF, so it must not reach the user as a 400.
    """
    expected_pages = list(page_numbers)
    try:
        entries = json.loads(reply)["pages"]
        sides_by_page = {int(entry["page"]): str(entry["side"]).strip().lower() for entry in entries}
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Page side classification returned an unreadable reply for pages {expected_pages}.") from exc

    if len(entries) != len(expected_pages) or sorted(sides_by_page) != expected_pages:
        raise RuntimeError(
            f"Page side classification returned pages {sorted(sides_by_page)}, expected {expected_pages}."
        )
    unknown_sides = sorted({side for side in sides_by_page.values() if side not in _PAGE_SIDES})
    if unknown_sides:
        raise RuntimeError(f"Page side classification returned unknown side(s) {unknown_sides}.")

    return [sides_by_page[page_number] for page_number in expected_pages]


def _side_classification_content(document: fitz.Document, page_numbers: Sequence[int]) -> List[Dict[str, Any]]:
    """Prompt plus a labeled thumbnail per page. Callers hold PYMUPDF_LOCK."""
    content: List[Dict[str, Any]] = [{"type": "text", "text": CLASSIFY_CHECK_SIDES_PROMPT}]
    for page_number in page_numbers:
        content.append({"type": "text", "text": f"Page {page_number}"})
        content.append(_png_image_part(_render_page_png(document, page_number - 1, _SIDE_CLASSIFICATION_DPI)))
    return content


def _classify_batch(llm: Any, content: List[Dict[str, Any]], page_numbers: Sequence[int]) -> List[str]:
    for attempt in range(1, _SIDE_CLASSIFICATION_ATTEMPTS + 1):
        response = llm.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        try:
            return _parse_page_sides(response.choices[0].message.content, page_numbers)
        except RuntimeError as exc:
            if attempt == _SIDE_CLASSIFICATION_ATTEMPTS:
                raise
            logger.warning(
                "outside_scholarships.pairing: attempt %s of %s: %s; retrying",
                attempt,
                _SIDE_CLASSIFICATION_ATTEMPTS,
                exc,
            )


def _classify_page_sides(
    document: fitz.Document,
    page_count: int,
    llm: Any,
    max_concurrency: Optional[int],
) -> List[str]:
    """Label every page of the PDF as a check front or back, in page order.

    Batches are independent, so each is sent as soon as its thumbnails render, while earlier
    batches are still waiting on the model.
    """
    batch_count = math.ceil(page_count / _SIDE_CLASSIFICATION_BATCH_SIZE)
    worker_count = max(1, min(batch_count, max_concurrency or batch_count))
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        batches = []
        for batch_start in range(0, page_count, _SIDE_CLASSIFICATION_BATCH_SIZE):
            batch_end = min(batch_start + _SIDE_CLASSIFICATION_BATCH_SIZE, page_count)
            # Label pages with their PDF page numbers so logs and errors match what the user sees.
            page_numbers = list(range(batch_start + 1, batch_end + 1))
            with PYMUPDF_LOCK:
                content = _side_classification_content(document, page_numbers)
            batches.append(pool.submit(_classify_batch, llm, content, page_numbers))
        # Collect in page order, not completion order, so every side stays with its page.
        return [side for batch in batches for side in batch.result()]


def _group_pages_by_check(sides: Sequence[str]) -> List[Tuple[int, Optional[int]]]:
    """Group 0-based page indexes into (front, back or None) per check.

    Every check starts with its front; a back belongs to the front directly before it.
    """
    checks: List[Tuple[int, Optional[int]]] = []
    for page_index, side in enumerate(sides):
        if side == _FRONT_SIDE:
            checks.append((page_index, None))
            continue
        if not checks or checks[-1][1] is not None:
            raise ValueError(
                f"Page {page_index + 1} looks like the back of a check, but there is no check front "
                "right before it. Put each check's front first, followed by its back, and upload again."
            )
        checks[-1] = (checks[-1][0], page_index)
    return checks


def pair_pages_node(state: OrchestratorState, config: RunnableConfig) -> Dict[str, Any]:
    """Read PDF bytes/folder inputs, detect each page's side, and group pages per check.

    Each check is its front page, followed by its back when one was scanned. Full-resolution
    images are rendered later by each check's worker, so checks start without waiting on them.
    """
    pdf_bytes_list: List[bytes] = list(state.get("pdf_files_bytes") or [])

    if not pdf_bytes_list and state.get("pdf_folder"):
        folder = state["pdf_folder"]
        for filename in sorted(os.listdir(folder)):
            if not filename.lower().endswith(".pdf"):
                continue
            with open(os.path.join(folder, filename), "rb") as file_handle:
                pdf_bytes_list.append(file_handle.read())

    if not pdf_bytes_list:
        logger.info("outside_scholarships.pairing: no PDFs found")
        return {"check_pairs": []}

    llm = config["configurable"]["llm"]
    paired_checks: List[CheckPair] = []
    check_index = 1

    for pdf_idx, pdf_bytes in enumerate(pdf_bytes_list, start=1):
        with PYMUPDF_LOCK:
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = document.page_count
        try:
            page_sides = _classify_page_sides(document, page_count, llm, config.get("max_concurrency"))
            logger.info(
                "outside_scholarships.pairing: pdf=%s pages=%s sides=%s",
                pdf_idx,
                page_count,
                ",".join(page_sides),
            )

            for front_page_idx, back_page_idx in _group_pages_by_check(page_sides):
                with PYMUPDF_LOCK:
                    pair_document = fitz.open()
                    pair_document.insert_pdf(
                        document,
                        from_page=front_page_idx,
                        to_page=front_page_idx if back_page_idx is None else back_page_idx,
                    )
                    pair_pdf_bytes = pair_document.tobytes()
                    pair_document.close()

                paired_checks.append({"check_index": check_index, "pair_pdf_bytes": pair_pdf_bytes})
                logger.info(
                    "outside_scholarships.pairing: check=%s front_page=%s back_page=%s",
                    check_index,
                    front_page_idx + 1,
                    None if back_page_idx is None else back_page_idx + 1,
                )
                check_index += 1
        finally:
            with PYMUPDF_LOCK:
                document.close()

    logger.info("outside_scholarships.pairing: total_checks=%s", len(paired_checks))
    return {"check_pairs": paired_checks}


def dispatch(state: OrchestratorState) -> List[Send]:
    """Fan-out: spawn one worker per paired check."""
    return [
        Send(
            "process_check",
            {
                "check_index": pair["check_index"],
                "pair_pdf_bytes": pair["pair_pdf_bytes"],
            },
        )
        for pair in state.get("check_pairs", [])
    ]


def _render_check_images(pair_pdf_bytes: bytes) -> Tuple[bytes, Optional[bytes]]:
    """Render a check's front and, when one was scanned, its back for field extraction."""
    with PYMUPDF_LOCK, fitz.open(stream=pair_pdf_bytes, filetype="pdf") as pair_document:
        front_image = _render_page_png(pair_document, 0, _PAGE_RENDER_DPI)
        back_image = _render_page_png(pair_document, 1, _PAGE_RENDER_DPI) if pair_document.page_count > 1 else None
    return front_image, back_image


def _parse_check_fields(reply: str, check_index: Optional[int]) -> Dict[str, Any]:
    """Read one check's extraction reply as a JSON object.

    Raises RuntimeError, not ValueError, for a bad reply: it is a model failure rather than a
    problem with the uploaded PDF, so it must not reach the user as a 400.
    """
    try:
        fields = json.loads(reply)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Field extraction for check {check_index} returned an unreadable reply.") from exc
    if not isinstance(fields, dict):
        raise RuntimeError(f"Field extraction for check {check_index} returned {type(fields).__name__}, not an object.")
    return fields


def _extract_check_fields(
    check_index: Optional[int],
    front_image: bytes,
    back_image: Optional[bytes],
    llm: Any,
) -> Dict[str, Any]:
    """Read one check's fields from its front (and back, if scanned) with a single vision call."""
    image_parts = [_png_image_part(front_image)]
    check_images_description = CHECK_IMAGES_FRONT_ONLY
    if back_image:
        image_parts.append(_png_image_part(back_image))
        check_images_description = CHECK_IMAGES_FRONT_AND_BACK

    prompt = EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT.replace("{check_images_description}", check_images_description)

    logger.info("outside_scholarships.extract: check=%s starting has_back=%s", check_index, back_image is not None)
    response = llm.chat.completions.create(
        model=_MODEL,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}, *image_parts],
            }
        ],
        response_format={"type": "json_object"},
    )

    reply_fields = _parse_check_fields(response.choices[0].message.content, check_index)
    check_fields = _normalize_check_fields(reply_fields)
    # Counts only: PIDs identify students. Listed minus kept is what was not a nine-digit PID, or a repeat.
    logger.info(
        "outside_scholarships.extract: check=%s listed_pid_count=%s pid_count=%s",
        check_index,
        len(_pid_candidates(reply_fields)),
        len(check_fields["pid_list"]),
    )
    return check_fields


def process_check_node(state: WorkerState, config: RunnableConfig) -> Dict[str, Any]:
    """Worker: render one check's pages and read its fields with one vision LLM call.

    Only check_results (an operator.add reducer) is written back to the shared graph state,
    so parallel workers never collide on a single-value key. The check index travels in
    metadata so aggregate_node can restore check order.
    """
    check_index = state.get("check_index")
    front_image, back_image = _render_check_images(state["pair_pdf_bytes"])
    check_fields = _extract_check_fields(check_index, front_image, back_image, config["configurable"]["llm"])
    return {"check_results": [{**check_fields, "metadata": {"check_index": check_index}}]}


def aggregate_node(state: OrchestratorState) -> Dict[str, Any]:
    """Collect worker results and return stable, check-index ordered output."""
    checks = list(state.get("check_results") or [])
    checks_with_position = list(enumerate(checks))
    sorted_checks = sorted(
        checks_with_position,
        key=lambda item: (
            item[1].get("metadata", {}).get("check_index") is None,
            item[1].get("metadata", {}).get("check_index", 0),
            item[0],
        ),
    )
    return {"final_payload": {"checks": [item[1] for item in sorted_checks]}}
