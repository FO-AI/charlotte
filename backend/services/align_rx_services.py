from config import get_logger
from .data_loaders import AlignRxDataLoader
from .azure_services import AlignRxSearchService, BlobStorageClient
from .parsers import AlignRxParser
from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse
from config import Settings
from datetime import datetime
from typing import Dict
import pandas as pd
import os
from azure.search.documents import SearchClient
logger = get_logger(__name__)
settings = Settings()

class DuplicateReportError(Exception):
    pass

async def export_alignrx_range_service(start: str, end: str, search_client: SearchClient):
    """Export AlignRx reports between start and end dates to Excel and stream the file."""
    try:
        loader = AlignRxDataLoader(start, end, search_client)
        records = loader._load_search_records(start, end)
        df = loader.to_dataframe(records)
        analyses = loader.analyze(df)
        excel_path = loader._default_output_path(start, end)
        path = loader.export_to_excel(df, analyses, excel_path)
        filename = os.path.basename(path)
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename
        )
    except Exception as e:
        logger.error(f"Error exporting AlignRx range: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting AlignRx range: {str(e)}")

def df_to_records(d):
    if d is None or getattr(d, 'empty', True):
        return []
    # Convert to dict first, then replace NaN values with None for JSON serialization
    records = d.to_dict(orient="records")
    # Clean NaN values and convert date objects to strings
    cleaned_records = []
    for record in records:
        cleaned_record = {}
        for key, value in record.items():
            # Check if value is NaN using pandas isna (handles all NaN types)
            if pd.isna(value):
                cleaned_record[key] = None
            # Convert date objects to strings (YYYY-MM-DD format)
            elif hasattr(value, 'strftime'):
                cleaned_record[key] = value.strftime("%Y-%m-%d")
            else:
                cleaned_record[key] = value
        cleaned_records.append(cleaned_record)
    return cleaned_records


async def analyze_alignrx_range_service(start: str, end: str, search_client: SearchClient):


    """Analyze AlignRx reports between start and end dates (YYYY-MM-DD)."""
    try:
        loader = AlignRxDataLoader(start, end, search_client)
        records = loader._load_search_records(start, end)
        df = loader.to_dataframe(records)
        analyses = loader.analyze(df)
        return {
            "success": True,
            "range": {"start": start, "end": end},
            "row_count": len(df) if df is not None else 0,
            "analyses": {
                "summary_totals": df_to_records(analyses.get("summary_totals")),
                "daily_totals": df_to_records(analyses.get("daily_totals")),
                "by_destination": df_to_records(analyses.get("by_destination")),
                "by_sender": df_to_records(analyses.get("by_sender")),
            },
        }
    except Exception as e:
        logger.error(f"Error analyzing AlignRx range: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing AlignRx range: {str(e)}")

async def upload_alignrx_report_service(blob_client: BlobStorageClient, user: Dict, file: UploadFile, search_client: SearchClient):
    """Upload AlignRx Excel report, parse it, and index parsed data into Azure AI Search."""
    try:
        # Validate file type (AlignRx reports are Excel)
        allowed_extensions = {'.xlsx', '.xls'}
        file_extension = os.path.splitext(file.filename)[1].lower()

        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(sorted(allowed_extensions))}"
            )
        

        # Read file content
        file_content = await file.read()

        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        # Persist to a temporary file for parser consumption
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            tmp.write(file_content)
            temp_path = tmp.name

        parsed_record = None
        parse_error = None
        is_duplicate_in_index = False
        schema_validation_failed = False
        try:
            parser = AlignRxParser(blob_client, search_client)
            parsed_record = parser.parse_excel_report(temp_path)
        except DuplicateReportError as dup_error:
            # Report already exists in search index - handle gracefully
            is_duplicate_in_index = True
            parse_error = str(dup_error)
            logger.info(f"AlignRx report already exists in search index: {file.filename}")
        except ValueError as validation_error:
            # Schema mismatch - parsing incomplete (missing required fields)
            schema_validation_failed = True
            parse_error = str(validation_error)
            logger.warning(f"Schema validation failed for {file.filename}: {parse_error}")
        except Exception as e:
            parse_error = str(e)
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

        # If parsing failed due to schema validation, reject immediately without uploading blob
        if schema_validation_failed:
            raise HTTPException(
                status_code=422,
                detail=f"Schema validation failed: {parse_error}. The file does not match the expected AlignRx report format."
            )

        # If parsing failed for other reasons (not schema validation), also reject
        if not parsed_record:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse AlignRx report{': ' + parse_error if parse_error else ''}"
            )

        # If report already exists in search index, reject without uploading blob
        if is_duplicate_in_index:
            raise HTTPException(
                status_code=409,
                detail=f"Report already exists in search index. The file data matches an existing report with the same date, destination, and payment amount."
            )

        # Use original filename so Azure duplicate detection can work
        blob_name = file.filename

        # Upload the raw file to Blob Storage (no overwrite)
        # Only upload if parsing succeeded
        # Run blob operations in executor with timeout to avoid blocking the event loop
        try:
            blob_client.upload_blob(blob_name, file_content, overwrite=False)
            duplicate = False
        except Exception as upload_error:
            if "BlobAlreadyExists" in str(upload_error) or "already exists" in str(upload_error).lower():
                # File already exists in blob storage
                raise HTTPException(
                    status_code=409,
                    detail=f"File '{file.filename}' already exists in the container"
                )
            else:
                raise upload_error

        # Enrich parsed record with storage metadata
        try:
            blob_url = blob_client.get_blob_url(blob_name)
        except Exception:
            blob_url = None
        
        

        # Ensure the indexed source_file reflects the actual uploaded blob, not a temp path used for parsing
        parsed_record["source_file"] = blob_name
        parsed_record["blob_name"] = blob_name
        if blob_url:
            parsed_record["blob_url"] = blob_url
        parsed_record["uploaded_at"] = datetime.utcnow().isoformat() + "Z"
        if user and isinstance(user, dict):
            parsed_record["uploaded_by"] = user.get("email")
        
    

        # Prepare and upload parsed document to Azure AI Search (AlignRx index)
        # Run indexing in executor to avoid blocking the event loop
        index_success = False
        try:
            # Normalize fields to match index schema
            index_doc = {
                "report_id": parsed_record.get("report_id") or parsed_record.get("id"),
                "source_file": parsed_record.get("source_file") or blob_name,
                "pay_date": parsed_record.get("pay_date") or parsed_record.get("date"),
                "destination": parsed_record.get("destination"),
                "processing_fee": parsed_record.get("processing_fee"),
                "payment_amount": parsed_record.get("payment_amount"),
                "central_payments": parsed_record.get("central_payments") or [],
            }

            # Remove keys with None to avoid schema mismatches
            index_doc = {k: v for k, v in index_doc.items() if v is not None}

            alignrx_search = AlignRxSearchService( search_client=search_client)
            index_success = alignrx_search.upload_documents([index_doc])
        except Exception as e:
            logger.error(f"Error uploading parsed AlignRx document to search index: {str(e)}")
            # Do not fail the entire request if indexing fails; report partial success

        user_email = user.get('email', 'unknown') if user and isinstance(user, dict) else 'unknown'
        logger.info(f"AlignRx report processed: {blob_name} by user {user_email}; indexed={index_success}")

        return {
            "success": True,
            "message": "AlignRx report uploaded and processed",
            "duplicate": duplicate,
            "filename": file.filename,
            "blob_name": blob_name,
            "blob_url": blob_url,
            "parsed": parsed_record,
            "indexed": index_success
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading AlignRx report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload AlignRx report: {str(e)}")