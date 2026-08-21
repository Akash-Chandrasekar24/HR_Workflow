import structlog
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["HR Command Center Portal"])

TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "web" / "templates" / "hr_portal.html"


@router.get("/", response_class=HTMLResponse, summary="HR Command Center Web Portal Home")
@router.get("/hr-portal", response_class=HTMLResponse, summary="HR Command Center Web Portal Dashboard")
async def render_hr_portal():
    """
    Renders the executive GWC DATA.AI HR Command Center Web Portal UI.
    Allows HR recruiters to launch batch screening drives using Google Spreadsheet & Drive URLs,
    view candidate evaluation tables, schedule MS Teams technical interviews, and export ledgers.
    """
    if not TEMPLATE_PATH.exists():
        raise HTTPException(status_code=404, detail="HR Portal template file not found.")

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content)
