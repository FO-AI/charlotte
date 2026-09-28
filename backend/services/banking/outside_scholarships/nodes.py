import base64
import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

import fitz  # PyMuPDF
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from langgraph.types import RunnableConfig, Send

from config import get_logger
from prompts.outside_scholarship import (
    CHECK_IMAGES_FRONT_AND_BACK,
    CHECK_IMAGES_FRONT_ONLY,
    CLASSIFY_CHECK_SIDES_PROMPT,
    VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT,
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

_REQUIRED_FIELDS = (
    "amount",
    "check_number",
    "name",
    "provider",
    "scholarship_name",
)
_EMPTY_MARKERS = {"", "null", "none", "n/a", "na", "unknown", "not found", "not provided"}

_PID_DIGIT_COUNT = 10
_PID_CONTEXT_CAPTURE_RE = re.compile(r"\bpid(?:s)?\b", re.IGNORECASE)
_PID_TOKEN_RE = re.compile(r"[A-Z0-9-]{4,}", re.IGNORECASE)
_PID_FALLBACK_RE = re.compile(r"\bP\d{6,10}\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"\$?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}")
_CHECK_NUMBER_RE = re.compile(
    r"(?:check\s*(?:number|no\.?|#)|no\.?)\s*[:#]?\s*([A-Z0-9-]{3,})",
    re.IGNORECASE,
)
_SCHOLARSHIP_LINE_RE = re.compile(r"([A-Z0-9][A-Z0-9 .,'&()/-]*SCHOLARSHIP[A-Z0-9 .,'&()/-]*)", re.IGNORECASE)


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


def _normalize_check_number(value: Any) -> Optional[str]:
    raw = _clean_optional(value)
    if raw is None:
        return None
    normalized = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    return normalized or None


def _normalize_pid(value: Any) -> Optional[str]:
    """Keep student PIDs only. A PID is exactly 10 digits; drop approval numbers."""
    raw = _clean_optional(value)
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) != _PID_DIGIT_COUNT:
        return None
    return digits


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


def _normalize_candidate(candidate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = candidate if isinstance(candidate, dict) else {}

    raw_pids = data.get("pid_list", [])
    if isinstance(raw_pids, str):
        pid_candidates: Sequence[Any] = re.split(r"[\n,;/]+", raw_pids)
    elif isinstance(raw_pids, list):
        pid_candidates = raw_pids
    else:
        pid_candidates = []

    normalized = {
        "pid_list": _dedupe_pids(pid_candidates),
        "amount": _normalize_amount(data.get("amount")),
        "check_number": _normalize_text(data.get("check_number")),
        "name": _normalize_text(data.get("name")),
        "provider": _normalize_text(data.get("provider")),
        "scholarship_name": _normalize_text(data.get("scholarship_name")),
    }
    return normalized


def _extract_text_from_di_result(analyze_result: Any) -> Tuple[List[str], str]:
    lines: List[str] = []

    for page in getattr(analyze_result, "pages", []) or []:
        for line in getattr(page, "lines", []) or []:
            content = _clean_optional(getattr(line, "content", None))
            if content:
                lines.append(content)

    content_text = _clean_optional(getattr(analyze_result, "content", None))
    if not lines and content_text:
        lines = [ln.strip() for ln in content_text.splitlines() if ln.strip()]

    full_text = "\n".join(lines) if lines else (content_text or "")
    return lines, full_text


def _extract_kv_map(analyze_result: Any) -> Dict[str, str]:
    kv_map: Dict[str, str] = {}

    for pair in getattr(analyze_result, "key_value_pairs", []) or []:
        key = _clean_optional(getattr(getattr(pair, "key", None), "content", None))
        value = _clean_optional(getattr(getattr(pair, "value", None), "content", None))
        if key and value:
            kv_map.setdefault(key.casefold(), value)

    return kv_map


def _kv_value(kv_map: Dict[str, str], labels: Sequence[str]) -> Optional[str]:
    for key, value in kv_map.items():
        if any(label in key for label in labels):
            return value
    return None


def _extract_pid_candidates(lines: Sequence[str], full_text: str, kv_map: Dict[str, str]) -> List[str]:
    pid_candidates: List[str] = []

    for key, value in kv_map.items():
        if "pid" in key:
            pid_candidates.extend(_PID_TOKEN_RE.findall(value))

    for line in lines:
        if not _PID_CONTEXT_CAPTURE_RE.search(line):
            continue
        for token in _PID_TOKEN_RE.findall(line):
            token_upper = token.upper()
            if token_upper in {"PID", "PIDS"}:
                continue
            if token_upper.isalpha():
                continue
            pid_candidates.append(token)

    if not pid_candidates:
        pid_candidates.extend(_PID_FALLBACK_RE.findall(full_text))

    return _dedupe_pids(pid_candidates)


def _extract_amount(lines: Sequence[str], kv_map: Dict[str, str]) -> Optional[str]:
    amount_from_kv = _kv_value(kv_map, ["amount", "check amount", "total"])
    if amount_from_kv:
        normalized = _normalize_amount(amount_from_kv)
        if normalized:
            return normalized

    for line in lines:
        lower_line = line.casefold()
        if "amount" in lower_line or "$" in line or "total" in lower_line:
            matches = _AMOUNT_RE.findall(line)
            if matches:
                normalized = _normalize_amount(matches[-1])
                if normalized:
                    return normalized

    for line in lines:
        matches = _AMOUNT_RE.findall(line)
        if matches:
            normalized = _normalize_amount(matches[-1])
            if normalized:
                return normalized

    return None


def _extract_check_number(lines: Sequence[str], kv_map: Dict[str, str]) -> Optional[str]:
    check_from_kv = _kv_value(kv_map, ["check number", "check no", "check #", "number"])
    if check_from_kv:
        return _normalize_text(check_from_kv)

    for line in lines:
        match = _CHECK_NUMBER_RE.search(line)
        if match:
            return _normalize_text(match.group(1))

    return None


def _extract_name(lines: Sequence[str], kv_map: Dict[str, str]) -> Optional[str]:
    from_kv = _kv_value(kv_map, ["payee", "student name", "pay to", "name"])
    if from_kv:
        return _normalize_text(from_kv)

    for idx, line in enumerate(lines):
        lower_line = line.casefold()
        if "pay to the order of" in lower_line:
            parts = re.split(r"pay to the order of", line, flags=re.IGNORECASE)
            tail = _normalize_text(parts[-1]) if parts else None
            if tail:
                return tail
            if idx + 1 < len(lines):
                next_line = _normalize_text(lines[idx + 1])
                if next_line:
                    return next_line

    return None


def _extract_provider(lines: Sequence[str], kv_map: Dict[str, str]) -> Optional[str]:
    from_kv = _kv_value(kv_map, ["provider", "payer", "remitter", "issuer", "from"])
    if from_kv:
        return _normalize_text(from_kv)

    ignored_tokens = ("pay to", "amount", "check", "memo", "pid", "date", "scholarship")
    for line in lines[:10]:
        normalized = _normalize_text(line)
        if not normalized:
            continue
        lower_line = normalized.casefold()
        if any(token in lower_line for token in ignored_tokens):
            continue
        if re.search(r"[A-Za-z]", normalized):
            return normalized

    return None


def _extract_scholarship_name(lines: Sequence[str], kv_map: Dict[str, str]) -> Optional[str]:
    from_kv = _kv_value(kv_map, ["scholarship", "award", "fund"])
    if from_kv:
        return _normalize_text(from_kv)

    for line in lines:
        if "scholarship" not in line.casefold():
            continue
        match = _SCHOLARSHIP_LINE_RE.search(line)
        if match:
            return _normalize_text(match.group(1))
        return _normalize_text(line)

    return None


def _extract_di_candidate(analyze_result: Any) -> Dict[str, Any]:
    lines, full_text = _extract_text_from_di_result(analyze_result)
    kv_map = _extract_kv_map(analyze_result)

    candidate = {
        "pid_list": _extract_pid_candidates(lines, full_text, kv_map),
        "amount": _extract_amount(lines, kv_map),
        "check_number": _extract_check_number(lines, kv_map),
        "name": _extract_name(lines, kv_map),
        "provider": _extract_provider(lines, kv_map),
        "scholarship_name": _extract_scholarship_name(lines, kv_map),
    }
    return _normalize_candidate(candidate)


def _field_values_match(field: str, di_value: Any, llm_value: Any) -> bool:
    if di_value is None and llm_value is None:
        return True
    if di_value is None or llm_value is None:
        return False

    if field == "amount":
        return _normalize_amount(di_value) == _normalize_amount(llm_value)
    if field == "check_number":
        return _normalize_check_number(di_value) == _normalize_check_number(llm_value)

    normalized_di = _normalize_text(di_value)
    normalized_llm = _normalize_text(llm_value)
    if normalized_di is None or normalized_llm is None:
        return False

    return normalized_di.casefold() == normalized_llm.casefold()


def _reconcile_scalar_field(field: str, di_candidate: Dict[str, Any], llm_candidate: Dict[str, Any]) -> Dict[str, Any]:
    di_value = di_candidate.get(field)
    llm_value = llm_candidate.get(field)

    matched = _field_values_match(field, di_value, llm_value)
    selected_value = llm_value if llm_value is not None else di_value
    selected_source = "llm" if llm_value is not None else ("di" if di_value is not None else "none")

    return {
        "value": selected_value,
        "status": "match" if matched else "corrected",
        "selected_source": selected_source,
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


def _classify_page_sides(document: fitz.Document, llm: Any) -> List[str]:
    """Label every page of the PDF as a check front or back, in page order."""
    sides: List[str] = []
    for batch_start in range(0, document.page_count, _SIDE_CLASSIFICATION_BATCH_SIZE):
        batch_end = min(batch_start + _SIDE_CLASSIFICATION_BATCH_SIZE, document.page_count)
        # Label pages with their PDF page numbers so logs and errors match what the user sees.
        page_numbers = list(range(batch_start + 1, batch_end + 1))

        content: List[Dict[str, Any]] = [{"type": "text", "text": CLASSIFY_CHECK_SIDES_PROMPT}]
        for page_number in page_numbers:
            content.append({"type": "text", "text": f"Page {page_number}"})
            content.append(_png_image_part(_render_page_png(document, page_number - 1, _SIDE_CLASSIFICATION_DPI)))

        response = llm.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_object"},
        )
        sides.extend(_parse_page_sides(response.choices[0].message.content, page_numbers))
    return sides


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

    Each check is its front page, followed by its back when one was scanned.
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
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_sides = _classify_page_sides(document, llm)
            logger.info(
                "outside_scholarships.pairing: pdf=%s pages=%s sides=%s",
                pdf_idx,
                document.page_count,
                ",".join(page_sides),
            )

            for front_page_idx, back_page_idx in _group_pages_by_check(page_sides):
                front_image = _render_page_png(document, front_page_idx, _PAGE_RENDER_DPI)
                back_image = None
                if back_page_idx is not None:
                    back_image = _render_page_png(document, back_page_idx, _PAGE_RENDER_DPI)

                pair_document = fitz.open()
                pair_document.insert_pdf(
                    document,
                    from_page=front_page_idx,
                    to_page=front_page_idx if back_page_idx is None else back_page_idx,
                )
                pair_pdf_bytes = pair_document.tobytes()
                pair_document.close()

                paired_checks.append(
                    {
                        "check_index": check_index,
                        "front_image": front_image,
                        "back_image": back_image,
                        "pair_pdf_bytes": pair_pdf_bytes,
                    }
                )
                logger.info(
                    "outside_scholarships.pairing: check=%s front_page=%s back_page=%s",
                    check_index,
                    front_page_idx + 1,
                    None if back_page_idx is None else back_page_idx + 1,
                )
                check_index += 1
        finally:
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
                "front_image": pair["front_image"],
                "back_image": pair["back_image"],
                "pair_pdf_bytes": pair["pair_pdf_bytes"],
            },
        )
        for pair in state.get("check_pairs", [])
    ]


def _di_extract(state: WorkerState, config: RunnableConfig) -> Dict[str, Any]:
    """Document Intelligence first pass over a check's front page and back page, if any."""
    di_client = config["configurable"].get("document_intelligence_client")
    di_model_id = config["configurable"].get("document_intelligence_model_id", "prebuilt-layout")

    if di_client is None:
        raise RuntimeError("Document Intelligence client is not configured.")

    check_index = state.get("check_index")
    pair_pdf_bytes = state.get("pair_pdf_bytes")
    if not pair_pdf_bytes:
        raise ValueError("Missing paired PDF bytes for Document Intelligence extraction.")

    logger.info("outside_scholarships.di: check=%s starting model=%s", check_index, di_model_id)

    try:
        poller = di_client.begin_analyze_document(
            di_model_id,
            AnalyzeDocumentRequest(bytes_source=pair_pdf_bytes),
        )
    except TypeError:
        # Compatibility path for SDK variants expecting raw body + content_type kwargs.
        poller = di_client.begin_analyze_document(
            model_id=di_model_id,
            body=pair_pdf_bytes,
            content_type="application/pdf",
        )
    analyze_result = poller.result()
    di_candidate = _extract_di_candidate(analyze_result)

    logger.info("outside_scholarships.di: check=%s pid_count=%s", check_index, len(di_candidate["pid_list"]))
    return di_candidate


def _llm_verify(state: WorkerState, di_candidate: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """LLM verification/correction pass using the check's front (and back, if scanned) + DI first-pass fields."""
    llm = config["configurable"]["llm"]
    check_index = state.get("check_index")
    front_image = state.get("front_image")
    back_image = state.get("back_image")
    if not front_image:
        raise ValueError("Missing front check image for LLM verification.")

    image_parts = [_png_image_part(front_image)]
    check_images_description = CHECK_IMAGES_FRONT_ONLY
    if back_image:
        image_parts.append(_png_image_part(back_image))
        check_images_description = CHECK_IMAGES_FRONT_AND_BACK

    prompt = VERIFY_OUTSIDE_SCHOLARSHIP_PROMPT.replace(
        "{check_images_description}",
        check_images_description,
    ).replace(
        "{di_candidate_json}",
        json.dumps(di_candidate, ensure_ascii=False),
    )

    logger.info("outside_scholarships.llm_verify: check=%s starting has_back=%s", check_index, back_image is not None)
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

    llm_candidate = _normalize_candidate(json.loads(response.choices[0].message.content))
    logger.info("outside_scholarships.llm_verify: check=%s pid_count=%s", check_index, len(llm_candidate["pid_list"]))
    return llm_candidate


def _reconcile(
    check_index: Optional[int],
    di_candidate: Dict[str, Any],
    llm_candidate: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge DI first-pass + LLM verification into final check output."""
    merged_pid_list = _dedupe_pids(di_candidate.get("pid_list", []) + llm_candidate.get("pid_list", []))
    pid_status = "match" if di_candidate.get("pid_list", []) == llm_candidate.get("pid_list", []) else "corrected"

    reconciled_fields: Dict[str, Dict[str, Any]] = {}
    final_check = {
        "pid_list": merged_pid_list,
    }

    for field_name in _REQUIRED_FIELDS:
        reconciled = _reconcile_scalar_field(field_name, di_candidate, llm_candidate)
        final_check[field_name] = reconciled["value"]
        reconciled_fields[field_name] = {
            "status": reconciled["status"],
            "selected_source": reconciled["selected_source"],
        }

    final_check["metadata"] = {
        "hybrid_extraction": {
            "document_intelligence": True,
            "llm_verification": True,
        },
        "reconciliation": {
            "pid_list": {
                "status": pid_status,
                "selected_source": "union",
            },
            **reconciled_fields,
        },
        "candidates": {
            "di": di_candidate,
            "llm": llm_candidate,
        },
    }
    if check_index is not None:
        final_check["metadata"]["check_index"] = check_index

    logger.info(
        "outside_scholarships.reconcile: check=%s pid_count=%s",
        check_index,
        len(final_check["pid_list"]),
    )
    return final_check


def process_check_node(state: WorkerState, config: RunnableConfig) -> Dict[str, Any]:
    """Worker: DI extraction, LLM verification, and reconciliation for one check pair.

    All three steps run inside a single node so each Send branch keeps its intermediate
    candidates local. Only check_results (an operator.add reducer) is written back to the
    shared graph state, so parallel workers never collide on a single-value key.
    """
    di_candidate = _di_extract(state, config)
    llm_candidate = _llm_verify(state, di_candidate, config)
    final_check = _reconcile(state.get("check_index"), di_candidate, llm_candidate)
    return {"check_results": [final_check]}


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
