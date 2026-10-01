import asyncio
from datetime import datetime
from typing import Any, Dict, List

from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import StreamingResponse

from services.azure_services import AzureClient, GraphUserDirectory
from services.banking.outside_scholarships.active_directory_names import (
    active_directory_display_name,
    lookup_active_directory_names,
    lookup_pids,
)
from services.banking.outside_scholarships.graph import build_graph
from services.data_loaders import OutsideScholarshipsDataLoader
from config import get_logger

logger = get_logger(__name__)

# Checks processed at once per upload; also bounds concurrent side-classification calls.
# Without it the graph's thread pool defaults to CPUs + 4 workers: 6 on a 2-vCPU App Service
# instance. Raise it only if the Azure OpenAI deployment's quota allows more vision calls at once.
MAX_CONCURRENT_CHECKS = 16
# Keep in sync with frontend outside-scholarships-upload-modal MAX_FILE_SIZE.
MAX_UPLOAD_BYTES = 300 * 1024 * 1024


class OutsideScholarshipService:
    def __init__(self, azure_client: AzureClient, user_directory: GraphUserDirectory):
        self.azure_client = azure_client
        self.user_directory = user_directory
        self._graph = build_graph()

    async def upload_and_analyze_files(
        self,
        files: List[UploadFile],
        graph_access_token: str,
        aid_year: str | None = None,
        aid_term: str | None = None,
    ) -> Dict[str, Any]:
        """Accept one PDF, run extraction, look up AD names, and return a review preview."""
        if len(files) != 1:
            raise HTTPException(status_code=400, detail="Upload exactly one PDF file.")

        upload = files[0]
        try:
            filename = upload.filename or "uploaded.pdf"
            content_type = (upload.content_type or "").lower()
            is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
            if not is_pdf:
                raise HTTPException(status_code=400, detail="Only PDF files are supported.")

            pdf_bytes = await upload.read()
            if not pdf_bytes:
                raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")
            if len(pdf_bytes) > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"File size too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)}MB).",
                )

            try:
                loader = OutsideScholarshipsDataLoader(aid_year=aid_year, aid_term=aid_term)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            initial_state = {
                "pdf_folder": None,
                "pdf_files_bytes": [pdf_bytes],
                "check_pairs": [],
                "check_results": [],
                "final_payload": {},
            }
            config = {
                "max_concurrency": MAX_CONCURRENT_CHECKS,
                "configurable": {"llm": self.azure_client.llm},
            }

            logger.info("outside_scholarships.service: starting extraction for %s", filename)
            try:
                result = await asyncio.to_thread(self._graph.invoke, initial_state, config)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:
                logger.exception("outside_scholarships.service: extraction failed")
                raise HTTPException(status_code=500, detail="Failed to process outside scholarship PDF.") from exc

            payload = result.get("final_payload", {"checks": []})
            self._log_extracted_checks(payload)
            ad_by_pid = await lookup_active_directory_names(
                self.user_directory, payload.get("checks", []), graph_access_token
            )
            preview = self._build_preview_payload(
                filename=filename,
                aid_year=loader.aid_year,
                aid_term=loader.aid_term,
                checks=payload.get("checks", []),
                ad_by_pid=ad_by_pid,
            )
            preview_checks = preview.get("checks", [])
            # Size is dominated by JPEG data URLs on front_image/back_image.
            preview_image_chars = self._preview_image_char_count(preview_checks)
            logger.info(
                "outside_scholarships.service: preview ready checks=%s preview_image_chars≈%s",
                len(preview_checks),
                preview_image_chars,
            )
            return preview
        finally:
            await upload.close()

    async def lookup_active_directory_for_pids(
        self,
        pids: List[str],
        graph_access_token: str,
    ) -> Dict[str, Any]:
        results = await lookup_pids(self.user_directory, pids, graph_access_token)
        return {"pids": [{"pid": pid, "active_directory": results[pid]} for pid in results]}

    async def export_reviewed(
        self,
        payload: Dict[str, Any],
        reviewed_by: str,
        graph_access_token: str,
    ) -> StreamingResponse:
        """Build Excel after re-looking up Active Directory names (do not trust the client)."""
        reviewed_pids: List[str] = []
        for check in payload.get("checks") or []:
            if not isinstance(check, dict):
                continue
            reviewed = check.get("reviewed") if isinstance(check.get("reviewed"), dict) else {}
            for entry in reviewed.get("pids") or []:
                if isinstance(entry, dict) and entry.get("pid") is not None:
                    reviewed_pids.append(str(entry.get("pid")))
                elif entry is not None and str(entry).strip():
                    reviewed_pids.append(str(entry))

        ad_by_pid = await lookup_pids(self.user_directory, reviewed_pids, graph_access_token)
        ad_name_by_pid = {
            pid: active_directory_display_name(result) for pid, result in ad_by_pid.items()
        }

        try:
            loader = OutsideScholarshipsDataLoader(
                aid_year=payload.get("aid_year"),
                aid_term=payload.get("aid_term"),
                reviewed_by=reviewed_by,
                active_directory_names=ad_name_by_pid,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        excel_output = loader.build_reviewed_excel_bytes(payload)
        file_date = datetime.now().strftime("%Y%m%d")
        filename = f"outside_scholarships_{file_date}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            excel_output,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def process_folder(self, folder_path: str) -> Dict[str, Any]:
        initial_state = {
            "pdf_folder": folder_path,
            "pdf_files_bytes": [],
            "check_pairs": [],
            "check_results": [],
            "final_payload": {},
        }
        config = {
            "max_concurrency": MAX_CONCURRENT_CHECKS,
            "configurable": {"llm": self.azure_client.llm},
        }

        result = await asyncio.to_thread(self._graph.invoke, initial_state, config)
        payload = result.get("final_payload", {"checks": []})
        self._log_extracted_checks(payload)
        return payload

    @staticmethod
    def _preview_image_char_count(checks: Any) -> int:
        """Total character length of preview JPEG data URLs (front_image / back_image)."""
        total = 0
        for check in checks if isinstance(checks, list) else []:
            if not isinstance(check, dict):
                continue
            front = check.get("front_image") or ""
            back = check.get("back_image") or ""
            total += len(front) if isinstance(front, str) else 0
            total += len(back) if isinstance(back, str) else 0
        return total

    @staticmethod
    def _build_preview_payload(
        filename: str,
        aid_year: str,
        aid_term: str,
        checks: Any,
        ad_by_pid: Dict[str, Any],
    ) -> Dict[str, Any]:
        preview_checks: List[Dict[str, Any]] = []
        for check in checks if isinstance(checks, list) else []:
            if not isinstance(check, dict):
                continue
            pid_list = check.get("pid_list") if isinstance(check.get("pid_list"), list) else []
            pids = []
            for pid in pid_list:
                pid_text = str(pid).strip() if pid is not None else ""
                if not pid_text:
                    continue
                pid_digits = "".join(ch for ch in pid_text if ch.isdigit())
                pids.append(
                    {
                        "pid": pid_digits or pid_text,
                        "active_directory": ad_by_pid.get(
                            pid_digits or pid_text, {"status": "not_found", "name": None}
                        ),
                    }
                )
            metadata = check.get("metadata") if isinstance(check.get("metadata"), dict) else {}
            preview_checks.append(
                {
                    "check_index": metadata.get("check_index", check.get("check_index")),
                    "front_page": check.get("front_page"),
                    "back_page": check.get("back_page"),
                    "front_image": check.get("front_image"),
                    "back_image": check.get("back_image"),
                    "amount": check.get("amount"),
                    "check_number": check.get("check_number"),
                    "name": check.get("name"),
                    "provider": check.get("provider"),
                    "scholarship_name": check.get("scholarship_name"),
                    "pids": pids,
                }
            )
        return {
            "filename": filename,
            "aid_year": aid_year,
            "aid_term": aid_term,
            "checks": preview_checks,
        }

    @staticmethod
    def _log_extracted_checks(payload: Dict[str, Any]) -> None:
        checks = payload.get("checks") if isinstance(payload, dict) else None
        if not isinstance(checks, list):
            logger.info("outside_scholarships.service: extracted payload is not in expected format")
            return

        logger.info("outside_scholarships.service: extracted checks=%s", len(checks))
        for idx, check in enumerate(checks, start=1):
            if not isinstance(check, dict):
                logger.info("outside_scholarships.service: check_%s malformed record", idx)
                continue

            pid_count = len(check.get("pid_list", [])) if isinstance(check.get("pid_list"), list) else 0
            logger.info(
                "outside_scholarships.service: check_%s_extracted pid_count=%s "
                "has_amount=%s has_check_number=%s has_name=%s has_provider=%s has_scholarship_name=%s",
                idx,
                pid_count,
                check.get("amount") is not None,
                check.get("check_number") is not None,
                check.get("name") is not None,
                check.get("provider") is not None,
                check.get("scholarship_name") is not None,
            )
