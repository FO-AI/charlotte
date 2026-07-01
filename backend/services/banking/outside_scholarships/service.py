import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List

import fitz
from fastapi import HTTPException
from fastapi import UploadFile
from fastapi.responses import StreamingResponse

from services.azure_services import AzureClient
from services.banking.outside_scholarships.graph import build_graph
from services.data_loaders import OutsideScholarshipsDataLoader
from config import get_logger

logger = get_logger(__name__)


class OutsideScholarshipService:
    def __init__(self, azure_client: AzureClient):
        self.azure_client = azure_client
        self._graph = build_graph()

    async def upload_and_analyze_files(
        self,
        files: List[UploadFile],
        aid_year: str | None = None,
        aid_term: str | None = None,
    ) -> StreamingResponse:
        """Accept uploaded PDF files, run extraction, and return an Excel file."""
        if len(files) != 1:
            raise HTTPException(status_code=400, detail="Upload exactly one PDF file.")

        upload = files[0]
        filename = upload.filename or "uploaded.pdf"
        content_type = (upload.content_type or "").lower()
        is_pdf = content_type == "application/pdf" or filename.lower().endswith(".pdf")
        if not is_pdf:
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")

        pdf_bytes = await upload.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty.")

        self._validate_even_page_count(pdf_bytes)

        di_client = self.azure_client.get_di()
        if di_client is None:
            logger.error("outside_scholarships.service: Document Intelligence client not configured")
            raise HTTPException(
                status_code=500,
                detail="Document Intelligence client is not configured.",
            )

        initial_state = {
            "pdf_folder": None,
            "pdf_files_bytes": [pdf_bytes],
            "check_pairs": [],
            "check_results": [],
            "final_payload": {},
        }
        config = {
            "configurable": {
                "llm": self.azure_client.llm,
                "document_intelligence_client": di_client,
                "document_intelligence_model_id": self.azure_client.di_model_id,
            }
        }

        logger.info("outside_scholarships.service: starting hybrid extraction for %s", filename)
        try:
            result = await asyncio.to_thread(self._graph.invoke, initial_state, config)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("outside_scholarships.service: hybrid extraction failed")
            raise HTTPException(status_code=500, detail="Failed to process outside scholarship PDF.") from exc

        payload = result.get("final_payload", {"checks": []})
        self._log_extracted_checks(payload)
        return self._build_excel_response(payload, aid_year=aid_year, aid_term=aid_term)

    async def process_folder(self, folder_path: str) -> Dict[str, Any]:
        """Process all PDF checks found in a local folder."""
        di_client = self.azure_client.get_di()
        if di_client is None:
            raise RuntimeError("Document Intelligence client is not configured.")

        initial_state = {
            "pdf_folder": folder_path,
            "pdf_files_bytes": [],
            "check_pairs": [],
            "check_results": [],
            "final_payload": {},
        }
        config = {
            "configurable": {
                "llm": self.azure_client.llm,
                "document_intelligence_client": di_client,
                "document_intelligence_model_id": self.azure_client.di_model_id,
            }
        }

        result = await asyncio.to_thread(self._graph.invoke, initial_state, config)
        payload = result.get("final_payload", {"checks": []})
        self._log_extracted_checks(payload)
        return payload

    @staticmethod
    def _build_excel_response(
        extraction_payload: Dict[str, Any],
        aid_year: str | None = None,
        aid_term: str | None = None,
    ) -> StreamingResponse:
        try:
            loader = OutsideScholarshipsDataLoader(aid_year=aid_year, aid_term=aid_term)
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
    def _validate_even_page_count(pdf_bytes: bytes) -> None:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = document.page_count
        if page_count % 2 != 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid outside scholarship PDF: page count must be even so pages can be "
                    f"paired as front/back checks. Found {page_count} page(s)."
                ),
            )

    @staticmethod
    def _log_extracted_checks(payload: Dict[str, Any]) -> None:
        checks = payload.get("checks") if isinstance(payload, dict) else None
        if not isinstance(checks, list):
            logger.info("outside_scholarships.service: extracted payload is not in expected format")
            logger.info("outside_scholarships.service: payload=%s", json.dumps(payload, ensure_ascii=False))
            return

        logger.info("outside_scholarships.service: extracted checks=%s", len(checks))
        required_fields = ("pid_list", "amount", "check_number", "name", "provider", "scholarship_name")

        for idx, check in enumerate(checks, start=1):
            if not isinstance(check, dict):
                logger.info("outside_scholarships.service: check_%s=%s", idx, json.dumps(check, ensure_ascii=False))
                continue

            summary = {field: check.get(field) for field in required_fields}
            logger.info(
                "outside_scholarships.service: check_%s_extracted=%s",
                idx,
                json.dumps(summary, ensure_ascii=False),
            )
