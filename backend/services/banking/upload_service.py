import json
import asyncio
import io
from typing import List, Dict, Any
from datetime import datetime
from config import get_logger
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import pandas as pd
import pdfplumber
from prompts import BANKING_UPLOAD_PROMPT
from services.azure_services import AzureClient

# Setup Logging
logger = get_logger(__name__)

class BankingUploadService:
    def __init__(self, azure_client: AzureClient):
        self.azure_client = azure_client

    
    async def upload_and_analyze_files(self, files: List[UploadFile]) -> pd.DataFrame:
        """
        Uploads a list of files to the Azure Blob Storage and analyzes them with the LLM.
        """
        tasks = []
        for file in files:
            if file.content_type != "application/pdf":
                logger.warning(f"Skipping non-PDF file: {file.filename}")
                continue
            content = await file.read()
            tasks.append(self._process_single_file(file.filename, content))
        
        results = await asyncio.gather(*tasks)
        valid_results = [r for r in results if r is not None]
        if not valid_results:
            raise HTTPException(status_code=500, detail="Failed to extract data from any uploaded documents.")
        df = self._flatten_to_dataframe(valid_results)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Consolidated Data', merge_cells=True)
        output.seek(0)
        headers = {
            'Content-Disposition': f'attachment; filename="banking_files_{datetime.now().strftime("%Y%m%d")}.xlsx"'
        }
        return StreamingResponse(
            output, 
            headers=headers, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    async def _process_single_file(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        """
        Processes a single file and returns the analyzed data.
        """
        text = self._extract_text_from_pdf_bytes(file_bytes)
        return await self._analyze_document_with_llm(filename, text)

    def _extract_text_from_pdf_bytes(self, file_bytes: bytes) -> str:
        """
        Extracts raw text from a PDF file using pdfplumber.
        """
        text_content = ""
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"
        except Exception as e:
            logger.error(f"Error extracting PDF text: {e}")
            return ""
        return text_content

    async def _analyze_document_with_llm(self, filename: str, text: str) -> Dict[str, Any]:
        """
        Sends text to Azure OpenAI to classify and extract data.
        """
        if not text.strip():
            logger.warning(f"File {filename} is empty or unreadable.")
            return None
        

        try:
            response = await asyncio.to_thread(
                self.azure_client.llm.chat.completions.create,
                model='gpt-5-chat',
                messages=[
                    {"role": "system", "content": BANKING_UPLOAD_PROMPT},
                    {"role": "user", "content": f"Filename: {filename}\n\nDocument Text:\n{text[:15000]}"} # Truncate if too large, usually fits 128k context
                ],
                temperature=0.0, # Deterministic output
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            data['filename'] = filename # Append filename for reference
            return data

        except Exception as e:
            logger.error(f"Error processing {filename} with LLM: {e}")
            return None

    def _flatten_to_dataframe(self, processed_data: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Converts the list of JSON objects into a flat Pandas DataFrame for Excel export.
        """
        flat_rows = []
        
        for doc in processed_data:
            if not doc:
                continue
                
            report_type = doc.get("report_type", "Unknown")
            filename = doc.get("filename", "")
            
            for item in doc.get("line_items", []):
                flat_rows.append({
                    "Report Type": report_type,
                    "Source File": filename,
                    "Date": item.get("item_date"),
                    "Description": item.get("description"),
                    "Amount": item.get("amount"),
                    "Type": item.get("type")
                })
                
        df = pd.DataFrame(flat_rows)

        if df.empty:
            return df

        df = df[["Report Type", "Source File", "Date", "Description", "Amount", "Type"]]
        df.set_index(["Report Type", "Source File"], inplace=True)

        return df

    # --- API Endpoints ---
