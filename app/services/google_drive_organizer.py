"""
==============================================================================
GWC DATA.AI | Google Drive Folder Organizer & Cloud File Relocator
==============================================================================
Directly manages Google Drive folder discovery, subfolder creation, and resume file movement
using the Google Drive API v3 with credentials.json.

Folder Structure Managed:
📁 [Parent Drive Link] /
├── 📁 Selected /
│   ├── 📁 AI_Engineer /
│   ├── 📁 Full_Stack /
│   └── 📁 Data_Analyst /
└── 📁 Rejected /
    ├── 📁 AI_Engineer /
    ├── 📁 Full_Stack /
    └── 📁 Data_Analyst /
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
import structlog
from app.core.config import settings
from app.services.google_drive import GoogleDriveService

logger = structlog.get_logger(__name__)

ORGANIZED_RESUME_ROOT = Path("app/data/resumes_organized")
ORGANIZED_RESUME_ROOT.mkdir(parents=True, exist_ok=True)
CREDS_FILE_PATH = "credentials.json"


class GoogleDriveFolderOrganizerService:
    """
    Manages automated Google Drive folder discovery, creation, and resume file movement.
    Connects to Google Drive API v3 using credentials.json to modify cloud folders directly.
    Only Selected and Rejected folders (with role subfolders) are created — no Review_Pending.
    """

    def __init__(self, drive_service: Optional[GoogleDriveService] = None):
        self.drive_service = drive_service or GoogleDriveService()
        self.cloud_service = self._init_cloud_service()

    def _init_cloud_service(self):
        """Initializes Google Drive API v3 client via Service Account credentials.json if present."""
        if not os.path.exists(CREDS_FILE_PATH):
            logger.info("Google credentials.json not found; running in local mirror mode")
            return None
        try:
            from googleapiclient.discovery import build
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                CREDS_FILE_PATH,
                scopes=['https://www.googleapis.com/auth/drive']
            )
            service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive API v3 connected successfully via Service Account", email=creds.service_account_email)
            return service
        except Exception as e:
            logger.warning("Could not initialize Google Drive v3 client from credentials.json", error=str(e))
            return None

    @staticmethod
    def extract_folder_id(url_or_id: str) -> str:
        """Extracts Google Drive Folder ID from full URL, partial link, or raw ID."""
        if not url_or_id:
            return ""
        match = re.search(r"folders/([-\w]{25,})", str(url_or_id))
        if match:
            return match.group(1)
        match_id = re.search(r"[-\w]{25,}", str(url_or_id))
        return match_id.group(0) if match_id else str(url_or_id).strip()

    @staticmethod
    def normalize_role(job_role: str) -> str:
        """
        Normalizes candidate job roles into clean folder naming keys:
        - AI_Engineer
        - Full_Stack
        - Data_Analyst
        """
        if not job_role:
            return "AI_Engineer"
        role_lower = job_role.lower().strip()

        if any(k in role_lower for k in ["ai", "ml", "machine learning", "deep learning", "genai", "llm"]):
            return "AI_Engineer"
        elif any(k in role_lower for k in ["full stack", "fullstack", "frontend", "backend", "python dev", "react", "node", "software"]):
            return "Full_Stack"
        elif any(k in role_lower for k in ["data", "analyst", "analytics", "bi", "tableau", "power bi"]):
            return "Data_Analyst"
        
        clean = re.sub(r"[^\w\s-]", "", job_role).strip().replace(" ", "_")
        return clean or "AI_Engineer"

    @staticmethod
    def map_status_to_folder(status: str) -> str:
        """Maps candidate screening status to Selected or Rejected only (no Review_Pending)."""
        status_upper = (status or "").upper().strip()
        if status_upper in ["SHORTLISTED", "SELECTED", "ACCEPTED", "APPROVED", "HR_APPROVED"]:
            return "Selected"
        # Everything else (including HR_REVIEW, REJECTED, FAILED, DECLINED) goes to Rejected
        return "Rejected"

    def get_or_create_cloud_subfolder(self, parent_folder_id: str, folder_name: str) -> Optional[str]:
        """
        Queries Google Drive API for an existing subfolder; creates it if not found.
        """
        if not self.cloud_service or not parent_folder_id:
            # Re-attempt connection if credentials was added
            if os.path.exists(CREDS_FILE_PATH) and not self.cloud_service:
                self.cloud_service = self._init_cloud_service()
            if not self.cloud_service:
                return None

        try:
            # Look for exact matching folder name (supports both AI_Engineer and "AI engineer")
            clean_name = folder_name.replace("_", " ")
            query = f"'{parent_folder_id}' in parents and (name = '{folder_name}' or name = '{clean_name}') and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.cloud_service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
            files = results.get('files', [])

            if files:
                logger.info("Found existing Google Drive folder", name=files[0]['name'], id=files[0]['id'])
                return files[0]['id']

            # Create the folder in Google Drive
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_folder_id]
            }
            created = self.cloud_service.files().create(body=folder_metadata, fields='id, name', supportsAllDrives=True).execute()
            created_id = created.get('id')
            logger.info("Created new Google Drive folder via Service Account", name=folder_name, id=created_id)
            return created_id
        except Exception as e:
            logger.warning("Google Drive API folder discovery/creation warning", folder=folder_name, error=str(e))
            return None

    def organize_candidate_resume(
        self,
        candidate_id: str,
        candidate_name: str,
        job_role: str,
        status: str,
        resume_file_id_or_url: str,
        parent_folder_url_or_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Organizes candidate resume into the appropriate status and role subfolder.
        1. Cleans up from old status folder if candidate is relocated (e.g. Rejected -> Selected).
        2. Saves into local organized directory.
        3. Moves the file in Google Drive via Google Drive API v3.
        """
        parent_id = self.extract_folder_id(parent_folder_url_or_id or getattr(settings, "GOOGLE_DRIVE_FOLDER_URL", "1ffGKAYBJDhMVE6oqubPklYnK5NAdBxCZ0sF3HKsJB8XOcp8QwEWh6QGDUW2AKq7rWSDUhSKY"))
        status_folder = self.map_status_to_folder(status)
        role_folder = self.normalize_role(job_role)
        target_subpath = f"{status_folder}/{role_folder}"

        clean_cand_name = (candidate_name or "Applicant").replace(" ", "_").replace("/", "_")
        file_id = self.extract_folder_id(resume_file_id_or_url) or resume_file_id_or_url

        # 1. Clean up from previous opposing status folder if candidate is being relocated (e.g. Rejected -> Selected)
        for other_status in ["Selected", "Rejected"]:
            if other_status != status_folder:
                for old_file in ORGANIZED_RESUME_ROOT.glob(f"{other_status}/*/{candidate_id}_*"):
                    try:
                        if old_file.is_file():
                            old_file.unlink()
                            logger.info("Removed candidate resume from old status folder", old_path=str(old_file))
                    except Exception as clean_err:
                        logger.warning("Could not clean old status file", error=str(clean_err))

        # 2. Local Mirror Directory
        local_target_dir = ORGANIZED_RESUME_ROOT / status_folder / role_folder
        local_target_dir.mkdir(parents=True, exist_ok=True)

        local_file_path = None
        try:
            if file_id:
                file_bytes, orig_name, mime_type = self.drive_service.download_file(file_id)
                ext = Path(orig_name).suffix.lower() or ".pdf"
                local_file_path = local_target_dir / f"{candidate_id}_{clean_cand_name}{ext}"
                with open(local_file_path, "wb") as f:
                    f.write(file_bytes)
                logger.info("Saved resume into organized local folder", path=str(local_file_path))
        except Exception as e:
            logger.warning("Could not download file for local folder organization", error=str(e))

        # 3. Google Drive API Live Move (Drive v3)
        cloud_drive_status = "LOCAL_MIRROR"
        if parent_id and file_id:
            try:
                status_id = self.get_or_create_cloud_subfolder(parent_id, status_folder)
                if status_id:
                    role_id = self.get_or_create_cloud_subfolder(status_id, role_folder)
                    if role_id and self.cloud_service:
                        # Move file directly in Google Drive
                        file_obj = self.cloud_service.files().get(fileId=file_id, fields='parents', supportsAllDrives=True).execute()
                        previous_parents = ",".join(file_obj.get('parents', []))
                        self.cloud_service.files().update(
                            fileId=file_id,
                            addParents=role_id,
                            removeParents=previous_parents,
                            fields='id, parents',
                            supportsAllDrives=True
                        ).execute()
                        cloud_drive_status = "GOOGLE_DRIVE_MOVED"
                        logger.info("Successfully moved file in Google Drive via Service Account", file_id=file_id, target=target_subpath)
            except Exception as drive_err:
                logger.warning("Google Drive live move note", error=str(drive_err))

        folder_url = f"https://drive.google.com/drive/folders/{parent_id}" if parent_id else ""
        
        return {
            "status": "SUCCESS",
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "parent_folder_id": parent_id,
            "status_folder": status_folder,
            "role_folder": role_folder,
            "relative_folder_path": target_subpath,
            "parent_folder_url": folder_url,
            "local_mirror_path": str(local_file_path) if local_file_path else None,
            "cloud_drive_status": cloud_drive_status,
            "action": f"Moved resume of {candidate_name} to {target_subpath}"
        }


# Global singleton instance
google_drive_organizer = GoogleDriveFolderOrganizerService()
