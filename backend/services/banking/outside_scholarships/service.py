import asyncio
from datetime import datetime
from typing import Any, Dict, List

from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import StreamingResponse

from services.azure_services import AzureClient, GraphUserDirectory
from services.banking.outside_scholarships.active_directory_names import lookup_active_directory_names
from services.banking.outside_scholarships.graph import build_graph
from services.data_loaders import OutsideScholarshipsDataLoader
from config import get_logger

logger = get_logger(__name__)

# Checks processed at once per upload; also bounds concurrent side-classification calls.
# Without it the graph's thread pool defaults to CPUs + 4 workers: 6 on a 2-vCPU App Service
# instance. Raise it only if the Azure OpenAI deployment's quota allows more vision calls at once.
MAX_CONCURRENT_CHECKS = 16


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
    ) -> StreamingResponse:
        """Accept uploaded PDF files, run extraction, and return an Excel file.

        `graph_access_token` is the signed-in user's Microsoft Graph token, used to look
        up each PID's Active Directory name.
        """
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
            active_directory_names = await lookup_active_directory_names(
                self.user_directory, payload.get("checks", []), graph_access_token
            )
            return self._build_excel_response(
                payload, active_directory_names, aid_year=aid_year, aid_term=aid_term
            )
        finally:
            # Explicitly close uploaded file handle to avoid residual temp file handles.
            await upload.close()

    async def process_folder(self, folder_path: str) -> Dict[str, Any]:
        """Process all PDF checks found in a local folder."""
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
    def _build_excel_response(
        extraction_payload: Dict[str, Any],
        active_directory_names: Dict[str, str],
        aid_year: str | None = None,
        aid_term: str | None = None,
    ) -> StreamingResponse:
        try:
            loader = OutsideScholarshipsDataLoader(
                aid_year=aid_year,
                aid_term=aid_term,
                active_directory_names=active_directory_names,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        logger.info(
            "outside_scholarships.service: building excel aid_year=%s aid_term=%s",
            loader.aid_year,
            loader.aid_term,
        )
        excel_output = loader.build_excel_bytes(extraction_payload)
        file_date = datetime.now().strftime("%Y%m%d")
        filename = f"outside_scholarships_{file_date}.xlsx"
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(
            excel_output,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

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
            has_amount = check.get("amount") is not None
            has_check_number = check.get("check_number") is not None
            has_name = check.get("name") is not None
            has_provider = check.get("provider") is not None
            has_scholarship_name = check.get("scholarship_name") is not None
            logger.info(
                "outside_scholarships.service: check_%s_extracted pid_count=%s "
                "has_amount=%s has_check_number=%s has_name=%s has_provider=%s has_scholarship_name=%s",
                idx,
                pid_count,
                has_amount,
                has_check_number,
                has_name,
                has_provider,
                has_scholarship_name,
            )
