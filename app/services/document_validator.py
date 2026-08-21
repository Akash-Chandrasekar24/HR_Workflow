import hashlib
import structlog
from typing import Tuple
from app.core.config import settings

logger = structlog.get_logger(__name__)

# File magic byte signatures
PDF_MAGIC = b"%PDF-"
DOCX_MAGIC = b"PK\x03\x04"


class DocumentValidator:
    """
    Validates resume file size, MIME format using magic byte inspection, and generates SHA256 hash.
    """

    @staticmethod
    def validate_and_hash(file_bytes: bytes, filename: str) -> Tuple[bool, str, str, str]:
        """
        Validates file integrity.
        Returns: (is_valid, detected_format, sha256_hash, error_message)
        """
        if not file_bytes:
            return False, "UNKNOWN", "", "Empty file bytes provided."

        size_mb = len(file_bytes) / (1024 * 1024)
        if size_mb > settings.MAX_FILE_SIZE_MB:
            return False, "UNKNOWN", "", f"File size ({size_mb:.2f}MB) exceeds maximum limit of {settings.MAX_FILE_SIZE_MB}MB."

        # Compute SHA256 content hash for deduplication
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()

        # Magic byte validation
        if file_bytes.startswith(PDF_MAGIC):
            detected_format = "PDF"
        elif file_bytes.startswith(DOCX_MAGIC) or filename.lower().endswith(".docx"):
            detected_format = "DOCX"
        else:
            return False, "UNKNOWN", sha256_hash, "Unsupported file format. Only PDF and DOCX documents are supported."

        logger.info(
            "Document integrity validated successfully",
            filename=filename,
            format=detected_format,
            size_bytes=len(file_bytes),
            hash_prefix=sha256_hash[:10]
        )

        return True, detected_format, sha256_hash, ""
