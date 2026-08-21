import queue
import threading
import structlog
from app.schemas.application import ApplicationIngestRequest
from app.services.resume_processor import ResumeProcessorService

logger = structlog.get_logger(__name__)


class ApplicationTaskQueue:
    """
    In-Memory Background Task Queue for processing incoming candidate resume applications asynchronously.
    """

    def __init__(self):
        self.task_queue = queue.Queue()
        self.processor = ResumeProcessorService()
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Background resume processing task worker initialized.")

    def enqueue_application(self, payload: ApplicationIngestRequest):
        """Enqueues candidate submission for background worker processing."""
        self.task_queue.put(payload)
        logger.info("Enqueued application task", candidate_id=payload.candidate_id, queue_size=self.task_queue.qsize())

    def _worker_loop(self):
        """Worker loop executing processing tasks asynchronously."""
        while True:
            try:
                payload = self.task_queue.get()
                logger.info("Dequeued candidate application for processing", candidate_id=payload.candidate_id)
                self.processor.process_application(payload)
                self.task_queue.task_done()
            except Exception as e:
                logger.error("Exception in background worker loop", error=str(e))


# Global background queue instance
task_queue = ApplicationTaskQueue()
