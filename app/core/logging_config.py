"""
==============================================================================
GWC DATA.AI | Enterprise Logging & Debug Engine
==============================================================================
Provides structured, comprehensive, and easy-to-debug logging for:
- Resume Ingestion & Google Drive Downloads
- Gemini LLM & Heuristic Screening Decisions
- Technical Interviewer Assignments & Workload Tracker
- Human-in-the-Loop Overrides & Re-Evaluations
- Automated Email & Teams Meeting Dispatches
- Error Traces & Rate Limit Recovery

Log Files Created in `logs/`:
- `logs/workflow.log`: Clean, colorized/formatted readable operational log.
- `logs/workflow_debug.log`: Detailed verbose debug log with full payloads & tracebacks.
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import structlog

# Create logs directory
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)

WORKFLOW_LOG_PATH = LOGS_DIR / "workflow.log"
DEBUG_LOG_PATH = LOGS_DIR / "workflow_debug.log"


class HumanReadableFormatter(logging.Formatter):
    """
    Produces clean, beautiful, easy-to-read log lines for developers and HR admins.
    Format: [2026-08-20 12:08:15] [INFO] [AI_SCREENING] Candidate CAN-001 (Akash C) scored 90.57/100 -> SHORTLISTED
    """
    CATEGORY_ICONS = {
        "DEBUG": "🔍 [DEBUG]",
        "INFO": "ℹ️ [INFO]",
        "WARNING": "⚠️ [WARNING]",
        "ERROR": "❌ [ERROR]",
        "CRITICAL": "🚨 [CRITICAL]"
    }

    def format(self, record):
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level_icon = self.CATEGORY_ICONS.get(record.levelname, f"[{record.levelname}]")
        module_info = f"{record.module}:{record.lineno}"
        
        message = record.getMessage()
        
        # Format exception traceback if present
        exc_text = ""
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                exc_text = f"\n   ↳ [TRACEBACK]:\n{record.exc_text}"

        return f"[{timestamp}] {level_icon:<14} [{module_info:<22}] {message}{exc_text}"


def setup_enterprise_logging():
    """
    Initializes and attaches root log handlers to write both standard workflow logs and deep debug logs.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Remove existing handlers to avoid duplicate log outputs
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # 1. Operational Workflow Log Handler (INFO and above, 10MB max, 5 backups)
    workflow_handler = RotatingFileHandler(
        WORKFLOW_LOG_PATH,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    workflow_handler.setLevel(logging.INFO)
    workflow_handler.setFormatter(HumanReadableFormatter())
    root_logger.addHandler(workflow_handler)

    # 2. Detailed Verbose Debug Log Handler (DEBUG and above, 20MB max, 5 backups)
    debug_handler = RotatingFileHandler(
        DEBUG_LOG_PATH,
        maxBytes=20 * 1024 * 1024,  # 20 MB
        backupCount=5,
        encoding="utf-8"
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [%(levelname)-8s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root_logger.addHandler(debug_handler)

    # 3. Console / Stdout Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(HumanReadableFormatter())
    root_logger.addHandler(console_handler)

    # 4. Configure Structlog to forward through standard logging
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False) if os.name == 'nt' else structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.info("=" * 80)
    logging.info("🚀 GWC DATA.AI Recruitment Workflow System Started")
    logging.info(f"📁 Detailed Operational Log: {WORKFLOW_LOG_PATH.resolve()}")
    logging.info(f"🔍 Verbose Debug Trace Log: {DEBUG_LOG_PATH.resolve()}")
    logging.info("=" * 80)


def get_recent_logs(lines: int = 100) -> str:
    """Reads the last N lines of the workflow log for quick in-browser or API debugging."""
    if not WORKFLOW_LOG_PATH.exists():
        return "No log entries recorded yet."
    try:
        with open(WORKFLOW_LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading logs: {str(e)}"
