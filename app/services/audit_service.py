import csv
import json
import threading
import structlog
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime, timezone
from app.core.config import settings

logger = structlog.get_logger(__name__)

AUDIT_HEADERS = ["audit_id", "timestamp", "candidate_id", "actor", "event_type", "details"]


class AuditLogService:
    """
    Central Audit Logging Service for compliance, auditability, and traceability.
    Persists immutable audit event records to CSV ledger (app/data/audit_logs.csv).
    """

    def __init__(self, audit_filepath: str = None):
        self.filepath = Path(audit_filepath or (settings.BASE_DIR / "app" / "data" / "audit_logs.csv"))
        self._lock = threading.Lock()
        self._initialize_csv()

    def _initialize_csv(self):
        with self._lock:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            if not self.filepath.exists():
                with open(self.filepath, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(AUDIT_HEADERS)

    def log_event(self, candidate_id: str, actor: str, event_type: str, details: Dict[str, Any]) -> Dict[str, Any]:
        """Appends audit log entry."""
        with self._lock:
            audit_id = f"AUD-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
            timestamp = datetime.now(timezone.utc).isoformat()
            
            row_dict = {
                "audit_id": audit_id,
                "timestamp": timestamp,
                "candidate_id": candidate_id or "SYSTEM",
                "actor": actor,
                "event_type": event_type,
                "details": json.dumps(details)
            }

            with open(self.filepath, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=AUDIT_HEADERS)
                writer.writerow(row_dict)

            logger.info("Logged audit event", candidate_id=candidate_id, actor=actor, audit_event=event_type)
            return row_dict

    def get_audit_trail(self, candidate_id: str) -> List[Dict[str, Any]]:
        """Fetches complete audit trail history for a candidate."""
        with self._lock:
            if not self.filepath.exists():
                return []
            trail = []
            with open(self.filepath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("candidate_id") == candidate_id:
                        entry = dict(row)
                        try:
                            entry["details"] = json.loads(row.get("details", "{}"))
                        except Exception:
                            entry["details"] = {}
                        trail.append(entry)
            return trail


# Global Audit Service Instance
audit_service = AuditLogService()
