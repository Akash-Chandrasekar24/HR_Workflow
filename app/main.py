import time
import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import applications, rules, notifications, interviews, portal


from app.core.logging_config import setup_enterprise_logging, get_recent_logs, WORKFLOW_LOG_PATH, DEBUG_LOG_PATH

# Initialize Enterprise Structured Logging
setup_enterprise_logging()
logger = structlog.get_logger(__name__)



async def inbox_watcher_background_task():
    """
    Automated Background Scheduler:
    Polls Gmail inbox every 2 minutes (120s) for technical interviewer availability replies,
    parses timings via AI, generates Microsoft Teams meetings, and updates status to 'MEETING FIXED'.
    """
    from app.services.inbox_watcher_service import inbox_watcher
    logger.info("Initialized Automated 2-Minute Gmail Inbox Watcher Scheduler Task")
    while True:
        try:
            await asyncio.sleep(120)  # Check every 2 minutes
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(None, inbox_watcher.sync_inbox_replies)
            if results:
                logger.info("Automated Scheduler: Processed interviewer replies", count=len(results))
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("Error in background inbox scheduler", error=str(e))
            await asyncio.sleep(30)


def reset_all_application_data_on_startup():
    """
    Clears all candidate records, cached resume files, and processed email IDs
    on server start/restart so every session begins with a clean slate.
    """
    from pathlib import Path
    try:
        from app.services.csv_storage import CSVStorageService
        # 1. Clear candidate CSV and Excel ledgers
        CSVStorageService().clear_ledger()

        # 2. Clear cached downloaded resumes
        resumes_dir = Path("app/data/resumes")
        if resumes_dir.exists():
            for f in resumes_dir.glob("*"):
                if f.is_file():
                    try:
                        f.unlink()
                    except Exception:
                        pass

        # 3. Clear processed email IDs tracker
        processed_ids_file = Path("app/data/processed_email_ids.json")
        if processed_ids_file.exists():
            try:
                processed_ids_file.unlink()
            except Exception:
                pass

        logger.info("Application Startup: Cleared all previous candidate data and cached files for a fresh session.")
    except Exception as e:
        logger.warning("Could not complete startup data cleanup", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Clear previous data if enabled
    if getattr(settings, "AUTO_CLEAR_DATA_ON_STARTUP", True):
        reset_all_application_data_on_startup()

    # Startup: Start background 2-minute inbox watcher scheduler
    scheduler_task = asyncio.create_task(inbox_watcher_background_task())
    yield
    # Shutdown: Cancel scheduler task
    scheduler_task.cancel()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise Automated Resume Screening Platform with Deterministic Scoring, Multi-Role Rules & Email Shortlist Digest.",
    debug=settings.DEBUG,
    lifespan=lifespan
)


# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time-Sec"] = f"{process_time:.4f}"
    return response


@app.get("/health", tags=["Monitoring"])
async def health_check():
    return {
        "status": "HEALTHY",
        "project": settings.PROJECT_NAME,
        "environment": settings.ENV
    }


@app.get("/ready", tags=["Monitoring"])
async def readiness_check():
    return {
        "status": "READY",
        "services": {
            "api": "UP",
            "storage": "UP"
        }
    }


from fastapi.responses import FileResponse, PlainTextResponse
from app.api.routes import applications, rules, notifications, interviews, portal, referrals

# Include Core API Routers
app.include_router(applications.router, prefix="/api/v1")
app.include_router(rules.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
app.include_router(interviews.router, prefix="/api/v1")
app.include_router(referrals.router, prefix="/api/v1")
app.include_router(portal.router)


@app.get("/api/v1/system/logs", tags=["System Diagnostics"])
async def view_recent_system_logs(lines: int = 150):

    """
    Returns the most recent N lines of the detailed operational workflow log.
    Useful for instant debugging and monitoring pipeline operations.
    """
    log_content = get_recent_logs(lines=lines)
    return PlainTextResponse(content=log_content, media_type="text/plain")


@app.get("/api/v1/system/download-logs", tags=["System Diagnostics"])
async def download_workflow_log_file():
    """
    Downloads the complete operational workflow.log file.
    """
    if not WORKFLOW_LOG_PATH.exists():
        return PlainTextResponse(content="No log file exists yet.", status_code=404)
    return FileResponse(
        path=str(WORKFLOW_LOG_PATH),
        filename="gwc_recruitment_workflow.log",
        media_type="text/plain"
    )





if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
