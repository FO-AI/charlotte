from fastapi import HTTPException, UploadFile, Response, FileResponse
from typing import Dict
from services import BlobStorageClient, AzureClient
from config import get_logger
from services import EDIParser, MASTER_EDI_DataLoader, CHS_EDI_DataLoader
from schemas import EDIAnalysisRequest
import os
import tempfile
import heapq
from datetime import datetime
import pandas as pd
import json
import re
logger = get_logger(__name__)

class DuplicateReportError(Exception):
    pass

async def upload_service(file: UploadFile, user: Dict, blob_client: BlobStorageClient):

    try:
        # Validate file type
        allowed_extensions = {'.pdf', '.txt', '.csv', '.xlsx', '.xls'}
        file_extension = os.path.splitext(file.filename)[1].lower()

        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"File type {file_extension} not allowed. Allowed types: {', '.join(allowed_extensions)}"
            )

        # Read file content
        file_content = await file.read()

        
        if blob_client.container_client.get_blob_client(file.filename).exists():
            raise HTTPException(status_code=409, detail=f"File '{file.filename}' already exists in the container")

        if len(file_content) == 0:
            raise HTTPException(status_code=400, detail="File is empty")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp:
            tmp.write(file_content)
            temp_path = tmp.name
        
        parse_result = None
        parse_error = None
        is_file_duplicate = False
        chs_index_success = False
        all_index_success = False
        blob_name = file.filename

        try:
            parser = EDIParser()
            parse_result = parser.parse_edi_file(temp_path, blob_name)
        
            
            if not parse_result.get("chs_transactions"):
                logger.warning(f"No CHS transactions found in {blob_name}")

        
        # File-level duplicate: entire file already exists - reject completely
        except DuplicateReportError as dup_error:
            # Report already exists in search index - handle gracefully
            is_file_duplicate = True
            parse_error = str(dup_error)
            logger.info(f"EDI report already exists in search index: {file.filename}")
        except Exception as e:
            parse_error = str(e)
            logger.error(f"Error parsing EDI file: {parse_error}")
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass
        
        if not parse_result or not parse_result.get("all_transactions"):
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse EDI report{': ' + parse_error if parse_error else ''}"
            )
        
        # If entire file is duplicate, reject the upload
        if is_file_duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"Report already exists in search index: {parse_error}"
            )

        # Extract data from parse result
        all_transactions = parse_result.get("all_transactions", [])
        chs_transactions = parse_result.get("chs_transactions", [])
        chs_duplicate = parse_result.get("chs_duplicate", False)
        all_duplicate = parse_result.get("all_duplicate", False)
        
        # If all transactions are duplicates, reject the upload completely (no blob upload)
        if all_duplicate:
            raise HTTPException(
                status_code=409,
                detail=f"All transactions from file '{file.filename}' already exist in the master-edi search index. File upload rejected."
            )
        
        # Upload to Azure Blob Storage (after successful parsing and duplicate check)
        # Only upload if all_duplicate is false
        sample_transaction = all_transactions[0]
        sum_amount = sum(transaction.get("amount", 0) for transaction in all_transactions)
        metadata = {
            "effective_date": sample_transaction.get("effective_date", ""),
            "total_amount": sum_amount,
            "uploaded_by": user.get('email', 'unknown') if user and isinstance(user, dict) else 'unknown'
        }
        # Azure Blob Storage only allows metadata values as strings.
        # Ensure all metadata values are string type.
        str_metadata = {k: str(v) for k, v in metadata.items()}
        blob_client.upload_blob(blob_name, file_content, overwrite=False)
        blob_client.set_blob_metadata(blob_name, str_metadata)
        logger.info(f"File uploaded to blob storage: {blob_name} with metadata: {metadata}")

        # Index transactions in search index
        # Skip CHS indexing if trace numbers are duplicates
        if chs_duplicate:
            logger.warning(f"Skipping CHS transaction indexing due to duplicate trace numbers in CHS search index")
            chs_index_success = False  # Explicitly set to False since we're skipping
        elif chs_transactions:
            chs_index_success = parser.index_transactions(chs_transactions, blob_name, "edi-transactions")
        
        # Index all transactions to master-edi (all_duplicate check already handled above - upload rejected if true)
        if all_transactions:
            all_index_success = parser.index_transactions(all_transactions, blob_name, "master-edi")

        # Consider it successful if both indexes were updated successfully or if duplicates prevented CHS indexing
        # Note: all_duplicate is already handled above (upload rejected), so we won't reach here if all_duplicate is true
        index_success = (
            (chs_index_success or chs_duplicate or not chs_transactions) and 
            all_index_success
        )

        if index_success:
            if chs_duplicate:
                logger.info(f"Successfully indexed {len(all_transactions)} all transactions from {blob_name} (CHS transactions skipped due to duplicates)")
            else:
                logger.info(f"Successfully indexed {len(chs_transactions) if chs_transactions else 0} CHS transactions and {len(all_transactions)} all transactions from {blob_name}")
        else:
            logger.warning(f"Failed to index transactions from {blob_name}")

        user_email = user.get('email', 'unknown') if user and isinstance(user, dict) else 'unknown'
        logger.info(f"EDI report processed: {blob_name} by user {user_email}; indexed={index_success}")

        # Build message based on duplicate status
        # Note: all_duplicate is already handled above (upload rejected), so we won't reach here if all_duplicate is true
        message = "File uploaded and processed successfully"
        if chs_duplicate:
            message += " (CHS transactions skipped due to duplicates)"
        
        return {
            "success": True,
            "message": message,
            "filename": file.filename,
            "blob_name": blob_name,
            "size": len(file_content),
            "chs_transaction_count": len(chs_transactions) if chs_transactions else 0,
            "all_transaction_count": len(all_transactions) if all_transactions else 0,
            "chs_indexed": chs_index_success,
            "chs_duplicate": chs_duplicate,
            "all_indexed": all_index_success,
            "all_duplicate": False,  # If we reach here, all_duplicate is false (upload would have been rejected otherwise)
            "uploaded_by": user.get('email') if user and isinstance(user, dict) else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


async def get_dashboard_data_service(blob_client: BlobStorageClient):
    
    try:
        # Get the current status of the master edi storage files in the blob storage
       
        blob_list_iterator = blob_client.list_blobs(include_metadata=True)
        latest_three_files = heapq.nlargest(3, blob_list_iterator, key=lambda x: x.last_modified)
        if not latest_three_files:
            logger.warning(f"No files found in master-edi-reports")
            return {
                "edi_dashboard_data": None,
                "total_files": 0
            }
        latest_three_files_info = []

        for file in latest_three_files:
            uploaded_by = 'employee'
            
            # Get metadata from blob properties (metadata is now included in list_blobs with include_metadata=True)
            if file.metadata and file.metadata.get("uploaded_by"):
                uploaded_by = file.metadata.get("uploaded_by")
                logger.info(f"Found metadata for {file.name}: uploaded_by={uploaded_by}")
            else:
                # Fallback: fetch blob properties individually if metadata not in list response
                try:
                    blob_props = blob_client.get_blob_properties(file.name)
                    if blob_props.metadata and blob_props.metadata.get("uploaded_by"):
                        uploaded_by = blob_props.metadata.get("uploaded_by")
                        logger.info(f"Found metadata via get_blob_properties for {file.name}: uploaded_by={uploaded_by}")
                    else:
                        logger.debug(f"No metadata found for {file.name}, using default 'employee'")
                except Exception as e:
                    logger.warning(f"Error fetching metadata for {file.name}: {str(e)}, using default 'employee'")
            
            # Convert datetime to ISO format string for JSON serialization
            last_modified_str = file.last_modified.isoformat() if file.last_modified else None
            
            latest_three_files_info.append({
                "name": file.name,
                "last_modified": last_modified_str,
                "uploaded_by": uploaded_by
            })
        
        latest_file = latest_three_files_info[0]
        latest_time = latest_file.get("last_modified")
        logger.info(f'latest files info: {latest_three_files_info}')
        logger.info(f'latest time: {latest_time}')


        current_year = datetime.now().year
        current_month = datetime.now().month
        if current_month < 7:
            start_date = f"{current_year-1}-07-01"
            end_date = f"{current_year}-06-30"
        else:
            start_date = f"{current_year}-07-01"
            end_date = f"{current_year +1}-06-30"
        logger.info(f"Getting EDI dashboard data for {start_date} to {end_date}")
        loader = MASTER_EDI_DataLoader(start_date, end_date)
        edi_dashboard_data = loader.get_dashboard_data(start_date, end_date)
        logger.info(f"EDI dashboard data: {edi_dashboard_data}")
        return {
            "edi_dashboard_data": edi_dashboard_data,
            "latest_three_files": latest_three_files_info,
            "latest_time": latest_time
        }
    except Exception as e:
        logger.error(f"Error getting EDI dashboard data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting EDI dashboard data: {str(e)}")
    

async def analyze_edi_range_service(request: EDIAnalysisRequest, user: Dict, azure_client: AzureClient):
    try:
        if request.mode == "master":
            loader = MASTER_EDI_DataLoader(request.start, request.end)
        else:
            loader = CHS_EDI_DataLoader(request.start, request.end)

        records = loader.load_edi_json(request.start, request.end)
        df = loader.to_dataframe(records)
        analyses = loader.analyze(df)
        
        # Convert DataFrames to JSON-serializable structures
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

        # Generate AI overview using all analysis data
        ai_overview = None
        try:

            llm = azure_client.llm
            # Prepare all analysis data for the LLM
            all_analysis_data = {
                "summary_totals": df_to_records(analyses.get("summary_totals")),
                "daily_totals": df_to_records(analyses.get("daily_totals")),
                "by_originator": df_to_records(analyses.get("by_originator")),
                "by_receiver": df_to_records(analyses.get("by_receiver")),
            }
            
            # Import the prompt template
            from prompts import ai_overview_prompt
            
            data_json = json.dumps(all_analysis_data, indent=2)
            
            ai_response = llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": ai_overview_prompt},
                    {"role": "user", "content": f"Here is the analysis data:\n\n{data_json}"}
                ]
            )
            ai_overview = ai_response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Failed to generate AI overview: {e}")
            ai_overview = None

        return {
            "success": True,
            "range": {"start": request.start, "end": request.end},
            "row_count": len(df) if df is not None else 0,
            "analyses": {
                "summary_totals": df_to_records(analyses.get("summary_totals")),
                "daily_totals": df_to_records(analyses.get("daily_totals")),
                "by_originator": df_to_records(analyses.get("by_originator")),
                "by_receiver": df_to_records(analyses.get("by_receiver")),
                "ai_overview": ai_overview,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing EDI range: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error analyzing EDI range: {str(e)}")

async def export_edi_range_service(request: EDIAnalysisRequest, user: Dict):
    """Export EDI transactions between start and end dates to Excel and stream the file."""
    try:
        if request.mode == "master":
            loader = MASTER_EDI_DataLoader(request.start, request.end)
        else:
            loader = CHS_EDI_DataLoader(request.start, request.end)
            
        records = loader.load_edi_json(request.start, request.end)
        df = loader.to_dataframe(records)
        analyses = loader.analyze(df)
        excel_path = loader._default_output_path(request.start, request.end)
        path = loader.export_to_excel(df, analyses, excel_path)

        filename = os.path.basename(path)
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting EDI range: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error exporting EDI range: {str(e)}")
async def get_reports_service(user: Dict, page: int, page_size: int, blob_client: BlobStorageClient):


    """Get paginated list of EDI reports from Azure Blob Storage"""
    try:
        # Single API call - includes metadata AND properties
        blobs = list(blob_client.list_blobs(include_metadata=True))
        
        # Sort by last_modified (newest first)
        blobs.sort(key=lambda b: b.last_modified or datetime.min, reverse=True)
        
        # Paginate
        total_count = len(blobs)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_blobs = blobs[start_idx:end_idx]
        
        reports = []
        for blob in paginated_blobs:
            filename = blob.name
            metadata = blob.metadata or {}
            
            # Parse date from filename (e.g., EDI Remittance Advice Report_2063_20250819_chs.pdf)
            date_match = re.search(r'(\d{8})', filename)
            parsed_date = None
            if date_match:
                try:
                    parsed_date = datetime.strptime(date_match.group(1), '%Y%m%d').strftime('%Y-%m-%d')
                except ValueError:
                    pass
            
            reports.append({
                "filename": filename,
                "url": blob_client.get_blob_url(filename),
                "size": blob.size,
                "last_modified": blob.last_modified.isoformat() if blob.last_modified else None,
                "parsed_date": parsed_date,
                "effective_date": metadata.get("effective_date", "unknown"),
                "total_amount": metadata.get("total_amount", 0),
                "uploaded_by": metadata.get("uploaded_by", "unknown"),
                "content_type": blob.content_settings.content_type if blob.content_settings else "application/pdf"
            })
        
        return {
            "success": True,
            "reports": reports,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "retrieved_by": user.get('email') if user and isinstance(user, dict) else None
        }
        
    except Exception as e:
        logger.error(f"Error retrieving EDI reports: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve EDI reports: {str(e)}")

async def get_one_report_service(filename: str, user: Dict, blob_client: BlobStorageClient):
    """Get a specific EDI report file from Azure Blob Storage"""
    try:
        # Get blob content
        blob_content = blob_client.download_blob(filename)
        
        # Get blob properties for content type
        blob_props = blob_client.get_blob_properties(filename)
        content_type = blob_props.content_settings.content_type if blob_props.content_settings else "application/pdf"
        
        # Return file response
        return Response(
            content=blob_content.readall(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Error retrieving EDI report {filename}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve EDI report: {str(e)}")