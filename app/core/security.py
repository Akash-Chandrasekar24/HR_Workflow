import hmac
import hashlib
from fastapi import HTTPException, Security, Header, status
from app.core.config import settings


def verify_hmac_signature(
    raw_body: bytes,
    x_signature_sha256: str | None = Header(None, alias="X-Signature-SHA256")
) -> bool:
    """
    Verifies that incoming webhook requests from Google Apps Script have a valid HMAC-SHA256 signature.
    """
    if not settings.HMAC_SECRET or settings.HMAC_SECRET == "change-this-super-secret-hmac-key-for-google-apps-script":
        if settings.ENV == "development":
            # Allow skipping in dev if secret not configured
            return True

    if not x_signature_sha256:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing mandatory header: X-Signature-SHA256"
        )

    computed_hmac = hmac.new(
        key=settings.HMAC_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hmac.lower(), x_signature_sha256.lower()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid HMAC signature. Authorization failed."
        )

    return True
