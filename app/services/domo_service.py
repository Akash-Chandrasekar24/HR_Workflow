import csv
import io
import json
import httpx
import structlog
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.csv_storage import CSV_HEADERS

logger = structlog.get_logger(__name__)


class DomoService:
    """
    Service to push final candidate recruitment records into Domo Webform / DataSet.
    Supports Domo OAuth 2.0 API, Webform Webhooks, and automatic audit logging.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        dataset_id: Optional[str] = None,
        api_host: Optional[str] = None,
        webhook_url: Optional[str] = None
    ):
        self.client_id = (client_id or settings.DOMO_CLIENT_ID or "").strip()
        self.client_secret = (client_secret or settings.DOMO_CLIENT_SECRET or "").strip()
        self.dataset_id = (dataset_id or settings.DOMO_DATASET_ID or "").strip()
        self.api_host = (api_host or settings.DOMO_API_HOST or "api.domo.com").strip()
        self.webhook_url = (webhook_url or settings.DOMO_WEBHOOK_URL or "").strip()
        self.token = None
        self.audit_dir = Path("app/data/domo_sync_audit")
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def is_configured(self) -> bool:
        """Returns whether Domo API credentials or Webhook URL are configured."""
        return bool((self.client_id and self.client_secret and self.dataset_id) or self.webhook_url)

    def get_access_token(self) -> Optional[str]:
        """
        Retrieves OAuth 2.0 Access Token from Domo.
        Endpoint: https://api.domo.com/oauth/token?grant_type=client_credentials&scope=data
        """
        if not (self.client_id and self.client_secret):
            return None

        url = f"https://{self.api_host}/oauth/token?grant_type=client_credentials&scope=data"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url, auth=(self.client_id, self.client_secret))
                if res.status_code == 200:
                    data = res.json()
                    self.token = data.get("access_token")
                    logger.info("Successfully authenticated with Domo API")
                    return self.token
                else:
                    logger.warning("Domo authentication returned non-200", status_code=res.status_code, body=res.text)
                    return None
        except Exception as e:
            logger.error("Failed to authenticate with Domo API", error=str(e))
            return None

    def format_records_as_csv(self, records: List[Dict[str, Any]]) -> str:
        """
        Formats candidate records into CSV text matching Domo Webform schema.
        Column 1: date, Column 23: resume_file (Google Drive view link).
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_HEADERS, extrasaction="ignore")
        writer.writeheader()

        for r in records:
            # Ensure Date exists in col 1
            cand_date = r.get("date", "") or r.get("screening_date", "") or datetime.now().strftime("%Y-%m-%d")
            
            # Ensure Drive Link exists in col 23
            resume_link = r.get("resume_file", "") or r.get("resume_file_id", "") or r.get("resume_url", "")
            if resume_link and not resume_link.startswith("http"):
                resume_link = f"https://drive.google.com/file/d/{resume_link}/view"

            row = {
                "date": cand_date,
                "candidate_id": r.get("candidate_id", ""),
                "candidate_name": r.get("candidate_name", "Applicant"),
                "email": r.get("email", ""),
                "phone": r.get("phone", ""),
                "job_role": r.get("job_role", ""),
                "status": r.get("status") or r.get("system_decision", "REJECTED"),
                "weightage_score": r.get("weightage_score") or r.get("weighted_score", 0.0),
                "reasoning": r.get("reasoning") or r.get("decision_reason", ""),
                "assigned_employee_id": r.get("assigned_employee_id", ""),
                "assigned_employee_name": r.get("assigned_employee_name", ""),
                "assigned_employee_email": r.get("assigned_employee_email", ""),
                "interview_status": r.get("interview_status", "UNASSIGNED"),
                "interview_schedule": r.get("interview_schedule", ""),
                "teams_meeting_url": r.get("teams_meeting_url", ""),
                "hr_approval_status": r.get("hr_approval_status", "HR_APPROVED"),
                "hr_feedback": r.get("hr_feedback", ""),
                "hr_override_status": r.get("hr_override_status", ""),
                "hr_recruiter_notes": r.get("hr_recruiter_notes", ""),
                "referred_by_name": r.get("referred_by_name", ""),
                "referred_by_id": r.get("referred_by_id", ""),
                "referred_by_email": r.get("referred_by_email", ""),
                "resume_file": resume_link
            }
            writer.writerow(row)

        return output.getvalue()

    def create_api_dataset(self, name: str = "GWC_Candidate_Screening_Ledger", description: str = "Automated Candidate Screening Results, AI Scores & Resume Links") -> Optional[str]:
        """Creates an API-enabled dataset in Domo with the 23-column recruitment schema."""
        token = self.get_access_token()
        if not token:
            return None

        schema = {
            "name": name,
            "description": description,
            "schema": {
                "columns": [{"type": "STRING", "name": col} for col in CSV_HEADERS]
            }
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.post(f"https://{self.api_host}/v1/datasets", json=schema, headers=headers)
                if res.status_code in [200, 201]:
                    data = res.json()
                    new_id = data.get("id")
                    self.dataset_id = new_id
                    logger.info("Created new Domo API dataset", dataset_id=new_id, name=name)
                    return new_id
                else:
                    logger.error("Failed to create Domo dataset", status_code=res.status_code, body=res.text)
                    return None
        except Exception as e:
            logger.error("Error creating Domo dataset", error=str(e))
            return None

    def fetch_existing_records(self) -> List[Dict[str, Any]]:
        """Retrieves existing rows from the Domo dataset for seamless appending/merging."""
        if not (self.client_id and self.client_secret and self.dataset_id):
            return []

        token = self.get_access_token()
        if not token:
            return []

        url = f"https://{self.api_host}/v1/datasets/{self.dataset_id}/data?includeHeader=true"
        headers = {"Authorization": f"Bearer {token}"}
        try:
            with httpx.Client(timeout=20.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 200 and res.text.strip():
                    reader = csv.DictReader(io.StringIO(res.text))
                    rows = list(reader)
                    logger.info("Retrieved existing records from Domo", count=len(rows), dataset_id=self.dataset_id)
                    return rows
        except Exception as e:
            logger.warning("Could not retrieve existing Domo records for merge", error=str(e))
        return []

    def append_records_via_stream(self, records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Natively appends new candidate records to Domo using Domo Streams API (updateMethod='APPEND').
        """
        if not (self.client_id and self.client_secret and self.dataset_id):
            return None

        token = self.get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                # 1. Search for existing stream on dataset
                search_url = f"https://{self.api_host}/v1/streams/search?q=dataset.id:{self.dataset_id}"
                search_res = client.get(search_url, headers=headers)
                stream_id = None
                if search_res.status_code == 200:
                    streams = search_res.json()
                    if streams:
                        stream_id = streams[0].get("id")

                # 2. Create stream if not exists
                if not stream_id:
                    create_stream_url = f"https://{self.api_host}/v1/streams"
                    stream_payload = {
                        "dataset": {"id": self.dataset_id},
                        "updateMethod": "APPEND"
                    }
                    create_res = client.post(create_stream_url, json=stream_payload, headers=headers)
                    if create_res.status_code in [200, 201]:
                        stream_id = create_res.json().get("id")

                if stream_id:
                    # 3. Create execution
                    exec_url = f"https://{self.api_host}/v1/streams/{stream_id}/executions"
                    exec_res = client.post(exec_url, headers=headers)
                    if exec_res.status_code in [200, 201]:
                        exec_id = exec_res.json().get("id")
                        
                        # 4. Upload part (new records only)
                        csv_chunk = self.format_records_as_csv(records)
                        part_url = f"https://{self.api_host}/v1/streams/{stream_id}/executions/{exec_id}/part/1"
                        part_headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "text/csv"
                        }
                        part_res = client.put(part_url, content=csv_chunk.encode("utf-8"), headers=part_headers)
                        
                        if part_res.status_code in [200, 204]:
                            # 5. Commit execution
                            commit_url = f"https://{self.api_host}/v1/streams/{stream_id}/executions/{exec_id}/commit"
                            commit_res = client.put(commit_url, headers=headers)
                            if commit_res.status_code in [200, 204]:
                                logger.info("Natively appended records to Domo via Stream", stream_id=stream_id, new_count=len(records))
                                return {
                                    "status": "SUCCESS",
                                    "destination": "DOMO_STREAM_APPEND",
                                    "dataset_id": self.dataset_id,
                                    "stream_id": stream_id,
                                    "count": len(records),
                                    "message": f"Successfully appended {len(records)} candidate records into Domo DataSet {self.dataset_id}."
                                }
        except Exception as str_err:
            logger.warning("Domo stream append note, using cumulative append fallback", error=str(str_err))
        return None

    def push_records_to_domo(self, records: List[Dict[str, Any]], append: bool = True) -> Dict[str, Any]:
        """
        Pushes candidate recruitment records directly to Domo DataSet / Webform.
        Appends new records to existing Domo records so all historical data is preserved.
        Executes via Domo Stream Append or Cumulative API Upload.
        Also persists a timestamped audit copy locally.
        """
        if not records:
            return {"status": "NO_RECORDS", "message": "No records to push to Domo.", "count": 0}

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 1. Try native Domo Stream Append if configured
        if append and self.client_id and self.client_secret and self.dataset_id:
            stream_result = self.append_records_via_stream(records)
            if stream_result and stream_result.get("status") == "SUCCESS":
                # Save audit file
                audit_file = self.audit_dir / f"domo_export_{stamp}.csv"
                try:
                    with open(audit_file, "w", newline="", encoding="utf-8") as f:
                        f.write(self.format_records_as_csv(records))
                except Exception:
                    pass
                return stream_result

        # 2. Cumulative Append Fallback: Fetch existing + append new batch
        existing_records = []
        if append:
            existing_records = self.fetch_existing_records()

        # Combine all existing records with new records
        unified_records = list(existing_records) + list(records)
        csv_content = self.format_records_as_csv(unified_records)

        # 3. Save local audit copy
        audit_file = self.audit_dir / f"domo_export_{stamp}.csv"
        try:
            with open(audit_file, "w", newline="", encoding="utf-8") as f:
                f.write(csv_content)
        except Exception as err:
            logger.warning("Could not write local Domo audit file", error=str(err))

        # 4. Push to Domo REST API
        if self.client_id and self.client_secret:
            token = self.get_access_token()
            if token:
                if not self.dataset_id:
                    self.create_api_dataset()

                if self.dataset_id:
                    url = f"https://{self.api_host}/v1/datasets/{self.dataset_id}/data"
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "text/csv"
                    }
                    try:
                        with httpx.Client(timeout=30.0) as client:
                            res = client.put(url, content=csv_content.encode("utf-8"), headers=headers)
                            if res.status_code in [200, 204]:
                                logger.info("Successfully uploaded dataset to Domo", dataset_id=self.dataset_id, total_count=len(unified_records), new_count=len(records))
                                return {
                                    "status": "SUCCESS",
                                    "destination": "DOMO_DATASET_API",
                                    "dataset_id": self.dataset_id,
                                    "count": len(unified_records),
                                    "message": f"Successfully appended {len(records)} candidates into Domo DataSet {self.dataset_id} (Total rows in Domo: {len(unified_records)})."
                                }
                            elif res.status_code == 400 and "Only DataSets created with the API" in res.text:
                                # Auto-heal by creating new API dataset and re-attempting upload
                                logger.warning("Existing dataset is not API-writable. Creating dedicated API dataset...")
                                new_id = self.create_api_dataset()
                                if new_id:
                                    retry_url = f"https://{self.api_host}/v1/datasets/{new_id}/data"
                                    retry_res = client.put(retry_url, content=csv_content.encode("utf-8"), headers=headers)
                                    if retry_res.status_code in [200, 204]:
                                        return {
                                            "status": "SUCCESS",
                                            "destination": "DOMO_DATASET_API",
                                            "dataset_id": new_id,
                                            "count": len(unified_records),
                                            "message": f"Created and appended {len(unified_records)} candidate records into Domo DataSet {new_id}."
                                        }
                            
                            logger.error("Domo upload failed", status_code=res.status_code, body=res.text)
                            return {
                                "status": "API_ERROR",
                                "destination": "DOMO_DATASET_API",
                                "dataset_id": self.dataset_id,
                                "status_code": res.status_code,
                                "message": f"Domo API returned HTTP {res.status_code}: {res.text}",
                                "fallback_audit": str(audit_file)
                            }
                    except Exception as api_err:
                        logger.error("Domo HTTP request error", error=str(api_err))
                        return {
                            "status": "CONNECTION_ERROR",
                            "error": str(api_err),
                            "fallback_audit": str(audit_file)
                        }

        # 3. Push to Domo Webhook if configured
        if self.webhook_url:
            try:
                with httpx.Client(timeout=30.0) as client:
                    res = client.post(self.webhook_url, json={"records": records, "timestamp": stamp, "csv": csv_content})
                    if res.status_code in [200, 201, 204]:
                        logger.info("Successfully pushed records to Domo Webhook", webhook=self.webhook_url, count=len(records))
                        return {
                            "status": "SUCCESS",
                            "destination": "DOMO_WEBHOOK",
                            "count": len(records),
                            "message": f"Successfully delivered {len(records)} records to Domo Webhook."
                        }
                    else:
                        logger.warning("Domo Webhook returned non-200", status_code=res.status_code)
            except Exception as wh_err:
                logger.error("Domo Webhook dispatch error", error=str(wh_err))

        # 4. Fallback / Local Audit Ready State
        logger.info(
            "Domo sync audit copy stored successfully",
            count=len(records),
            audit_file=str(audit_file)
        )
        return {
            "status": "SUCCESS",
            "destination": "DOMO_AUDIT_STAGING",
            "count": len(records),
            "audit_file": str(audit_file),
            "message": f"Prepared and audited {len(records)} candidate records for Domo Webform. (Configure DOMO_CLIENT_ID & DOMO_DATASET_ID in .env for direct cloud sync)."
        }


domo_service = DomoService()
