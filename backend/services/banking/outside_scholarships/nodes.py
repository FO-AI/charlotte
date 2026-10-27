import base64
import json
import math
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
from langgraph.types import RunnableConfig, Send

from config import get_logger
from prompts.outside_scholarship import (
    CLASSIFY_CHECK_SIDES_PROMPT,
    EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT,
    EXTRACT_SUPPORTING_ROSTER_PROMPT,
    describe_check_images,
)
from services.banking.outside_scholarships.state import CheckPair, OrchestratorState, WorkerState
from services.data_loaders.outside_scholarships_json_to_excel import ALLOWED_AID_TERMS

logger = get_logger(__name__)
_MODEL = "gpt-5-chat"

_FRONT_SIDE = "front"
_BACK_SIDE = "back"
_SUPPORTING_SIDE = "supporting"
_PAGE_SIDES = {_FRONT_SIDE, _BACK_SIDE, _SUPPORTING_SIDE}
_PAGE_RENDER_DPI = 200
_ROSTER_RENDER_DPI = 250
_ROSTER_CROP_OVERLAP = 0.02
_ROSTER_TALL_PAGE_PX = 1200
_ROSTER_TRIM_PAD_PX = 12
_ROSTER_TRIM_STEP_PX = 4
_ROSTER_TRIM_WHITE_THRESHOLD = 245
# Preview JPEGs for the review UI: legible on screen, smaller than extraction PNGs.
_PREVIEW_JPEG_DPI = 150
_PREVIEW_JPEG_QUALITY = 75
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


def _pid_from_digits(digits: str) -> Optional[str]:
    # UNC student PIDs do not start with 0; padded row indexes are not PIDs.
    if not digits.isdecimal() or len(digits) != _PID_DIGIT_COUNT or digits.startswith("0"):
        return None
    return digits


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
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _pid_from_digits(str(value))
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return None
        return _pid_from_digits(str(int(value)))
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            return None
        return _pid_from_digits(str(int(value)))
    raw = _clean_optional(value)
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    return _pid_from_digits(digits)


def _pids_from_value(value: Any) -> List[str]:
    """Nine-digit PIDs found in one field value.

    Handles a bare PID, and a single string that also names an approval number
    (for example \"730123456 1380307\" or \"PID: 730123456 / 1380307\").
    """
    raw = _clean_optional(value)
    if raw is None:
        return []
    whole = _normalize_pid(raw)
    if whole:
        return [whole]

    found: List[str] = []
    seen = set()
    for token in re.split(r"[\s,;/|]+", raw):
        pid = _normalize_pid(token)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        found.append(pid)
    if found:
        return found

    # Standalone nine-digit runs that are not part of a longer number.
    for match in re.finditer(rf"(?<!\d)\d{{{_PID_DIGIT_COUNT}}}(?!\d)", raw):
        pid = _normalize_pid(match.group(0))
        if pid and pid not in seen:
            seen.add(pid)
            found.append(pid)
    return found


def _dedupe_pids(pid_values: Sequence[Any]) -> List[str]:
    normalized: List[str] = []
    seen = set()

    for value in pid_values:
        for pid in _pids_from_value(value):
            if pid in seen:
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


def _normalize_aid_term(value: Any) -> Optional[str]:
    """Keep only the upload codes. Any other wording from the model is dropped."""
    text = _normalize_text(value)
    if text is None:
        return None
    normalized = text.strip().upper()
    if normalized in ALLOWED_AID_TERMS:
        return normalized
    return None


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes"}


def _decimal_amount(value: Any) -> Optional[Decimal]:
    amount = _normalize_amount(value)
    if amount is None or not re.fullmatch(r"\d+(?:\.\d{2})", amount):
        return None
    try:
        return Decimal(amount)
    except InvalidOperation:
        return None


def _complete_pid_amount_split(
    pid_amounts: Sequence[Dict[str, Any]],
    check_amount: Any,
    pid_list: Sequence[str],
) -> bool:
    expected = _decimal_amount(check_amount)
    if expected is None or not pid_list:
        return False

    amounts_by_pid: Dict[str, List[Decimal]] = {pid: [] for pid in pid_list}
    for item in pid_amounts:
        pid = _normalize_pid(item.get("pid"))
        if pid not in amounts_by_pid:
            continue
        amount = _decimal_amount(item.get("amount"))
        if amount is None:
            return False
        amounts_by_pid[pid].append(amount)

    total = Decimal("0")
    for pid in pid_list:
        amounts = amounts_by_pid[pid]
        if len(amounts) != 1:
            return False
        total += amounts[0]
    return abs(total - expected) <= Decimal("0.01")


def _normalize_pid_amount_candidates(fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_amounts = fields.get("pid_amounts")
    if not isinstance(raw_amounts, list):
        return []

    normalized: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_amounts:
        if not isinstance(item, dict):
            continue
        pid = _normalize_pid(item.get("pid"))
        if not pid or pid in seen:
            continue
        amount = _normalize_amount(item.get("amount"))
        if amount is None:
            continue
        seen.add(pid)
        entry: Dict[str, Any] = {"pid": pid, "amount": amount}
        name = _normalize_text(item.get("name"))
        if name:
            entry["name"] = name
        scholarship_name = _normalize_text(item.get("scholarship_name"))
        if scholarship_name:
            entry["scholarship_name"] = scholarship_name
        normalized.append(entry)
    return normalized


def _normalize_pid_amounts(pid_amounts: Sequence[Dict[str, Any]], pid_list: Sequence[str]) -> List[Dict[str, Any]]:
    """Per-PID shares from supporting pages, limited to PIDs accepted for this check."""
    allowed_pids = set(pid_list)
    return [dict(item) for item in pid_amounts if item.get("pid") in allowed_pids]


def _normalize_check_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    pid_list = _dedupe_pids(_pid_candidates(fields))
    amount = _normalize_amount(fields.get("amount"))
    pid_amount_candidates = _normalize_pid_amount_candidates(fields)
    candidate_pids = [entry["pid"] for entry in pid_amount_candidates]
    is_multi_pid_roster = len(candidate_pids) > 1
    if is_multi_pid_roster and (
        not pid_list or _complete_pid_amount_split(pid_amount_candidates, amount, candidate_pids)
    ):
        pid_list = _dedupe_pids([*pid_list, *candidate_pids])
    return {
        "pid_list": pid_list,
        "pid_amounts": _normalize_pid_amounts(pid_amount_candidates, pid_list),
        "amount": amount,
        "check_number": _normalize_text(fields.get("check_number")),
        "name": _normalize_text(fields.get("name")),
        "provider": _normalize_text(fields.get("provider")),
        "scholarship_name": _normalize_text(fields.get("scholarship_name")),
        "aid_term": _normalize_aid_term(fields.get("aid_term")),
        "supporting_has_amount_and_pid": _truthy_flag(fields.get("supporting_has_amount_and_pid")),
    }


def _force_first_page_front(sides: Sequence[str]) -> List[str]:
    """Treat PDF page 1 as a check front so a classifier miss does not reject the upload."""
    if not sides:
        return []
    forced = list(sides)
    if forced[0] != _FRONT_SIDE:
        logger.warning(
            "outside_scholarships.pairing: forcing page 1 from %s to front",
            forced[0],
        )
        forced[0] = _FRONT_SIDE
    return forced


def _render_page_png(document: fitz.Document, page_index: int, dpi: int, rotate: int = 0) -> bytes:
    scale = dpi / 72
    matrix = fitz.Matrix(scale, scale)
    if rotate:
        matrix.prerotate(rotate)
    return document.load_page(page_index).get_pixmap(matrix=matrix).tobytes("png")


def _render_page_jpeg_data_url(document: fitz.Document, page_index: int, dpi: int) -> str:
    scale = dpi / 72
    pixmap = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(scale, scale))
    jpeg_bytes = pixmap.tobytes("jpeg", jpg_quality=_PREVIEW_JPEG_QUALITY)
    encoded = base64.b64encode(jpeg_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def _crop_png(png_bytes: bytes, crop: fitz.IRect) -> bytes:
    source = fitz.Pixmap(png_bytes)
    cropped = fitz.Pixmap(source.colorspace, crop, source.alpha)
    cropped.copy(source, crop)
    cropped.set_origin(0, 0)
    return cropped.tobytes("png")


def _trim_png_whitespace(png_bytes: bytes, pad: int = _ROSTER_TRIM_PAD_PX) -> bytes:
    """Crop near-white margins so a small table on a large page fills the image."""
    pixmap = fitz.Pixmap(png_bytes)
    width, height, channels = pixmap.width, pixmap.height, pixmap.n
    samples = pixmap.samples
    min_x, min_y = width, height
    max_x, max_y = 0, 0
    for y in range(0, height, _ROSTER_TRIM_STEP_PX):
        row = y * width * channels
        for x in range(0, width, _ROSTER_TRIM_STEP_PX):
            index = row + x * channels
            red, green, blue = samples[index], samples[index + 1], samples[index + 2]
            if (
                red < _ROSTER_TRIM_WHITE_THRESHOLD
                or green < _ROSTER_TRIM_WHITE_THRESHOLD
                or blue < _ROSTER_TRIM_WHITE_THRESHOLD
            ):
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if min_x > max_x or min_y > max_y:
        return png_bytes
    crop = fitz.IRect(
        max(0, min_x - pad),
        max(0, min_y - pad),
        min(width, max_x + _ROSTER_TRIM_STEP_PX + pad),
        min(height, max_y + _ROSTER_TRIM_STEP_PX + pad),
    )
    if crop.width < 32 or crop.height < 32 or (crop.width == width and crop.height == height):
        return png_bytes
    return _crop_png(png_bytes, crop)


def _supporting_roster_crops_unlocked(page_index: int, png_bytes: bytes) -> List[Tuple[str, bytes]]:
    pixmap = fitz.Pixmap(png_bytes)
    width = pixmap.width
    height = pixmap.height
    half_overlap = _ROSTER_CROP_OVERLAP / 2
    if height >= _ROSTER_TALL_PAGE_PX:
        first_boundary = 1 / 3
        second_boundary = 2 / 3
        top_end = max(1, min(height, round(height * (first_boundary + half_overlap))))
        middle_start = max(0, min(height - 1, round(height * (first_boundary - half_overlap))))
        middle_end = max(middle_start + 1, min(height, round(height * (second_boundary + half_overlap))))
        bottom_start = max(0, min(height - 1, round(height * (second_boundary - half_overlap))))
        return [
            (f"Supporting page {page_index} top", _crop_png(png_bytes, fitz.IRect(0, 0, width, top_end))),
            (
                f"Supporting page {page_index} middle",
                _crop_png(png_bytes, fitz.IRect(0, middle_start, width, middle_end)),
            ),
            (
                f"Supporting page {page_index} bottom",
                _crop_png(png_bytes, fitz.IRect(0, bottom_start, width, height)),
            ),
        ]
    top_end = max(1, min(height, round(height * (0.5 + half_overlap))))
    bottom_start = max(0, min(height - 1, round(height * (0.5 - half_overlap))))
    return [
        (f"Supporting page {page_index} top", _crop_png(png_bytes, fitz.IRect(0, 0, width, top_end))),
        (f"Supporting page {page_index} bottom", _crop_png(png_bytes, fitz.IRect(0, bottom_start, width, height))),
    ]


def _rotate_png_90_cw(png_bytes: bytes) -> bytes:
    with fitz.open(stream=png_bytes, filetype="png") as document:
        page = document.load_page(0)
        matrix = fitz.Matrix(1, 1)
        matrix.prerotate(90)
        return page.get_pixmap(matrix=matrix).tobytes("png")


def _render_supporting_roster_crops(
    pair_pdf_bytes: bytes,
    has_back: bool,
    rotate: int = 0,
    include_full: bool = False,
) -> List[Tuple[str, bytes]]:
    supporting_start = 2 if has_back else 1
    with PYMUPDF_LOCK, fitz.open(stream=pair_pdf_bytes, filetype="pdf") as pair_document:
        crops: List[Tuple[str, bytes]] = []
        for supporting_number, page_index in enumerate(range(supporting_start, pair_document.page_count), start=1):
            page_image = _trim_png_whitespace(
                _render_page_png(pair_document, page_index, _ROSTER_RENDER_DPI, rotate=rotate)
            )
            crops.extend(_supporting_roster_crops_unlocked(supporting_number, page_image))
            if include_full:
                crops.append((f"Supporting page {supporting_number} full", page_image))
    return crops


def _supporting_images_roster_crops(
    supporting_images: Sequence[bytes],
    rotate: int = 0,
    include_full: bool = False,
) -> List[Tuple[str, bytes]]:
    crops: List[Tuple[str, bytes]] = []
    with PYMUPDF_LOCK:
        for index, supporting_image in enumerate(supporting_images, start=1):
            page_image = _rotate_png_90_cw(supporting_image) if rotate else supporting_image
            page_image = _trim_png_whitespace(page_image)
            crops.extend(_supporting_roster_crops_unlocked(index, page_image))
            if include_full:
                crops.append((f"Supporting page {index} full", page_image))
    return crops


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
    """Label every page of the PDF as a check front, check back, or supporting page, in page order.

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


def _group_pages_by_check(sides: Sequence[str]) -> List[Dict[str, Any]]:
    """Group 0-based page indexes into one check: front, optional back, then supporting pages.

    A back belongs to the check in progress, including when a stub was scanned before the reverse.
    Supporting pages follow that check until the next front. A supporting page or a back before the
    first front, or a second back for the same check, is an upload error.
    """
    checks: List[Dict[str, Any]] = []
    for page_index, side in enumerate(sides):
        page_number = page_index + 1
        if side == _FRONT_SIDE:
            checks.append({"front": page_index, "back": None, "supporting": []})
            continue
        if not checks:
            raise ValueError(
                f"Page {page_number} is not a check front, and there is no check before it. "
                "Put each check's front first, then its back if you have one, then that check's "
                "letters or forms, and upload again."
            )
        current = checks[-1]
        if side == _BACK_SIDE:
            if current["back"] is not None:
                raise ValueError(
                    f"Page {page_number} looks like another back for the check that starts on "
                    f"page {current['front'] + 1}. Each check can have only one back."
                )
            current["back"] = page_index
            continue
        if side == _SUPPORTING_SIDE:
            current["supporting"].append(page_index)
            continue
        raise ValueError(f"Page {page_number} has an unknown side {side!r}.")
    return checks


def pair_pages_node(state: OrchestratorState, config: RunnableConfig) -> Dict[str, Any]:
    """Read PDF bytes/folder inputs, detect each page's side, and group pages per check.

    Each check is its front page, then its back when one was scanned, then that check's supporting
    pages. Full-resolution images are rendered later by each check's worker, so checks start
    without waiting on them.
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
            page_sides = _force_first_page_front(
                _classify_page_sides(document, page_count, llm, config.get("max_concurrency"))
            )
            logger.info(
                "outside_scholarships.pairing: pdf=%s pages=%s sides=%s",
                pdf_idx,
                page_count,
                ",".join(page_sides),
            )

            for grouped in _group_pages_by_check(page_sides):
                front_page_idx = grouped["front"]
                back_page_idx = grouped["back"]
                supporting_indexes = grouped["supporting"]
                # Front, then the back, then supporting pages. A scan can place the back after a stub.
                ordered_indexes = [front_page_idx]
                if back_page_idx is not None:
                    ordered_indexes.append(back_page_idx)
                ordered_indexes.extend(supporting_indexes)
                with PYMUPDF_LOCK:
                    pair_document = fitz.open()
                    for source_index in ordered_indexes:
                        pair_document.insert_pdf(document, from_page=source_index, to_page=source_index)
                    pair_pdf_bytes = pair_document.tobytes()
                    pair_document.close()

                front_page = front_page_idx + 1
                back_page = None if back_page_idx is None else back_page_idx + 1
                supporting_pages = [index + 1 for index in supporting_indexes]
                paired_checks.append(
                    {
                        "check_index": check_index,
                        "pair_pdf_bytes": pair_pdf_bytes,
                        "front_page": front_page,
                        "back_page": back_page,
                        "supporting_pages": supporting_pages,
                    }
                )
                logger.info(
                    "outside_scholarships.pairing: check=%s front_page=%s back_page=%s supporting_pages=%s",
                    check_index,
                    front_page,
                    back_page,
                    supporting_pages,
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
                "front_page": pair["front_page"],
                "back_page": pair.get("back_page"),
                "supporting_pages": list(pair.get("supporting_pages") or []),
            },
        )
        for pair in state.get("check_pairs", [])
    ]


def _render_check_images(
    pair_pdf_bytes: bytes,
    has_back: bool,
) -> Tuple[bytes, Optional[bytes], List[bytes], str, Optional[str], List[str]]:
    """PNG bytes for extraction plus JPEG data URLs for the review UI (one open, one lock).

    Page 0 is the front. The back is page 1 only when this check has one. Later pages are
    supporting documents, including when there is no back.
    """
    with PYMUPDF_LOCK, fitz.open(stream=pair_pdf_bytes, filetype="pdf") as pair_document:
        front_image = _render_page_png(pair_document, 0, _PAGE_RENDER_DPI)
        back_image = _render_page_png(pair_document, 1, _PAGE_RENDER_DPI) if has_back else None
        supporting_start = 2 if has_back else 1
        supporting_images = [
            _render_page_png(pair_document, page_index, _PAGE_RENDER_DPI)
            for page_index in range(supporting_start, pair_document.page_count)
        ]
        front_preview = _render_page_jpeg_data_url(pair_document, 0, _PREVIEW_JPEG_DPI)
        back_preview = (
            _render_page_jpeg_data_url(pair_document, 1, _PREVIEW_JPEG_DPI) if has_back else None
        )
        supporting_previews = [
            _render_page_jpeg_data_url(pair_document, page_index, _PREVIEW_JPEG_DPI)
            for page_index in range(supporting_start, pair_document.page_count)
        ]
    return front_image, back_image, supporting_images, front_preview, back_preview, supporting_previews


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


def _parse_supporting_roster_rows(reply: str, check_index: Optional[int]) -> List[Dict[str, Any]]:
    try:
        fields = json.loads(reply)
        rows = fields["rows"]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f"Roster extraction for check {check_index} returned an unreadable reply.") from exc
    if not isinstance(fields, dict):
        raise RuntimeError(f"Roster extraction for check {check_index} returned {type(fields).__name__}, not an object.")
    if not isinstance(rows, list):
        raise RuntimeError(f"Roster extraction for check {check_index} returned rows as {type(rows).__name__}, not a list.")
    return [row for row in rows if isinstance(row, dict)]


def _labeled_image(label: str, png_bytes: bytes) -> List[Dict[str, Any]]:
    return [{"type": "text", "text": label}, _png_image_part(png_bytes)]


def _roster_name_key(value: Any) -> Optional[str]:
    raw = _clean_optional(value)
    if raw is None:
        return None
    letters = re.sub(r"[^a-z]+", "", raw.casefold())
    return letters or None


def _roster_fields_from_rows(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    pid_list: List[str] = []
    pid_amounts: List[Dict[str, Any]] = []
    seen_pids = set()
    seen_name_amounts = set()
    for row in rows:
        pid = _normalize_pid(row.get("pid"))
        if not pid or pid in seen_pids:
            continue
        name_key = _roster_name_key(row.get("name"))
        amount = _decimal_amount(row.get("amount"))
        # Overlapping crops can repeat a student with a 1–2 digit PID OCR miss. Same readable
        # name and share is that duplicate, not a second student.
        if name_key and amount is not None:
            identity = (name_key, amount)
            if identity in seen_name_amounts:
                continue
            seen_name_amounts.add(identity)
        seen_pids.add(pid)
        pid_list.append(pid)
        entry: Dict[str, Any] = {"pid": pid, "amount": row.get("amount")}
        if "name" in row:
            entry["name"] = row.get("name")
        if "scholarship_name" in row:
            entry["scholarship_name"] = row.get("scholarship_name")
        pid_amounts.append(entry)
    return {"pid_list": pid_list, "pid_amounts": pid_amounts}


def _roster_amount_count(rows: Sequence[Dict[str, Any]]) -> int:
    return sum(
        1
        for item in _roster_fields_from_rows(rows)["pid_amounts"]
        if _decimal_amount(item.get("amount")) is not None
    )


def _extract_supporting_roster_rows(
    check_index: Optional[int],
    supporting_images: Sequence[bytes],
    llm: Any,
    pair_pdf_bytes: Optional[bytes] = None,
    has_back: bool = False,
) -> List[Dict[str, Any]]:
    def extract_crop(label: str, supporting_image: bytes) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = [
            {"type": "text", "text": EXTRACT_SUPPORTING_ROSTER_PROMPT},
            *_labeled_image(label, supporting_image),
        ]
        response = llm.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        return _parse_supporting_roster_rows(response.choices[0].message.content, check_index)

    def crops_for_rotate(rotate: int) -> List[Tuple[str, bytes]]:
        include_full = rotate != 0
        if pair_pdf_bytes is not None:
            return _render_supporting_roster_crops(
                pair_pdf_bytes, has_back, rotate=rotate, include_full=include_full
            )
        return _supporting_images_roster_crops(
            supporting_images, rotate=rotate, include_full=include_full
        )

    def extract_crops(crops: Sequence[Tuple[str, bytes]]) -> Tuple[List[Dict[str, Any]], int]:
        rows_by_crop = [extract_crop(label, crop_image) for label, crop_image in crops]
        retry_count = 0
        if any(rows_by_crop):
            for crop_offset, crop_rows in enumerate(rows_by_crop):
                if crop_rows:
                    continue
                label, crop_image = crops[crop_offset]
                rows_by_crop[crop_offset] = extract_crop(label, crop_image)
                retry_count += 1
        rows = [row for crop_rows in rows_by_crop for row in crop_rows]
        return rows, retry_count

    crops = crops_for_rotate(0)
    rows, retry_count = extract_crops(crops)
    roster_fields = _roster_fields_from_rows(rows)
    kept_amount_count = _roster_amount_count(rows)
    rotate_used = 0
    if len(roster_fields["pid_list"]) >= 2 and kept_amount_count == 0:
        rotated_crops = crops_for_rotate(90)
        rotated_rows, rotated_retry_count = extract_crops(rotated_crops)
        rotated_amount_count = _roster_amount_count(rotated_rows)
        if rotated_amount_count > kept_amount_count:
            crops = rotated_crops
            rows = rotated_rows
            retry_count += rotated_retry_count
            kept_amount_count = rotated_amount_count
            roster_fields = _roster_fields_from_rows(rows)
            rotate_used = 90
    logger.info(
        "outside_scholarships.extract_roster_pages: crop_count=%s retry_count=%s rotate=%s "
        "kept_pid_count=%s kept_amount_count=%s",
        len(crops),
        retry_count,
        rotate_used,
        len(roster_fields["pid_list"]),
        kept_amount_count,
    )
    return rows


def _extract_check_fields(
    check_index: Optional[int],
    front_image: bytes,
    back_image: Optional[bytes],
    supporting_images: Sequence[bytes],
    llm: Any,
    pair_pdf_bytes: Optional[bytes] = None,
    has_back: bool = False,
) -> Dict[str, Any]:
    """Read one check, with its supporting pages, in a single vision call."""
    content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": EXTRACT_OUTSIDE_SCHOLARSHIP_PROMPT.replace(
                "{check_images_description}",
                describe_check_images(back_image is not None, len(supporting_images)),
            ),
        },
        *_labeled_image("Check front", front_image),
    ]
    if back_image:
        content.extend(_labeled_image("Check back", back_image))
    for index, supporting_image in enumerate(supporting_images, start=1):
        content.extend(_labeled_image(f"Supporting page {index}", supporting_image))

    logger.info(
        "outside_scholarships.extract: check=%s starting has_back=%s supporting_pages=%s",
        check_index,
        back_image is not None,
        len(supporting_images),
    )
    response = llm.chat.completions.create(
        model=_MODEL,
        messages=[{"role": "user", "content": content}],
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
    has_complete_multi_pid_split = _complete_pid_amount_split(
        check_fields["pid_amounts"],
        check_fields["amount"],
        check_fields["pid_list"],
    ) and len(check_fields["pid_list"]) >= 2
    if supporting_images and not has_complete_multi_pid_split:
        roster_rows = _extract_supporting_roster_rows(
            check_index,
            supporting_images,
            llm,
            pair_pdf_bytes=pair_pdf_bytes,
            has_back=has_back,
        )
        roster_fields = _roster_fields_from_rows(roster_rows)
        if len(roster_fields["pid_list"]) >= 2:
            check_fields = _normalize_check_fields({**check_fields, **roster_fields})
    return check_fields


def process_check_node(state: WorkerState, config: RunnableConfig) -> Dict[str, Any]:
    """Worker: render one check's pages and read its fields with one vision LLM call.

    Only check_results (an operator.add reducer) is written back to the shared graph state,
    so parallel workers never collide on a single-value key. The check index travels in
    metadata so aggregate_node can restore check order. Preview JPEGs and page numbers go
    on the check itself for the review UI.

    Extraction failures stay on this check so other checks in the PDF can still finish.
    """
    check_index = state.get("check_index")
    front_page = state.get("front_page")
    back_page = state.get("back_page")
    supporting_pages = list(state.get("supporting_pages") or [])
    pair_pdf_bytes = state["pair_pdf_bytes"]
    (
        front_image,
        back_image,
        supporting_images,
        front_preview,
        back_preview,
        supporting_previews,
    ) = _render_check_images(pair_pdf_bytes, back_page is not None)
    try:
        check_fields = _extract_check_fields(
            check_index,
            front_image,
            back_image,
            supporting_images,
            config["configurable"]["llm"],
            pair_pdf_bytes=pair_pdf_bytes,
            has_back=back_page is not None,
        )
        extraction_failed = False
    except Exception:
        logger.exception(
            "outside_scholarships.extract: check=%s failed; continuing with other checks",
            check_index,
        )
        check_fields = _normalize_check_fields({})
        extraction_failed = True
    return {
        "check_results": [
            {
                **check_fields,
                "extraction_failed": extraction_failed,
                "front_page": front_page,
                "back_page": back_page,
                "supporting_pages": supporting_pages,
                "front_image": front_preview,
                "back_image": back_preview,
                "supporting_images": supporting_previews,
                "metadata": {"check_index": check_index},
            }
        ]
    }


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
