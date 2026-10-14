"""SQLite-backed async job processor (PLAN.md §6).

Processes memo jobs sequentially without external brokers (no Celery/Redis).
"""
import asyncio
import logging
from collections.abc import Callable, Coroutine

from app.db import get_db

logger = logging.getLogger(__name__)

class JobWorker:
    def __init__(self, poll_interval_sec: float = 1.0):
        self.poll_interval = poll_interval_sec
        self.running = False

    async def start(self, handler: Callable[[str], Coroutine]):
        """Runs the worker loop, polling for queued jobs."""
        self.running = True
        logger.info("JobWorker started polling SQLite queue.")
        while self.running:
            try:
                job_id = self._claim_next_job()
                if job_id:
                    logger.info("Processing job %s", job_id)
                    try:
                        await handler(job_id)
                        self._complete_job(job_id)
                    except Exception as exc:
                        logger.exception("Job %s failed", job_id)
                        self._fail_job(job_id, str(exc))
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error("Error in job worker loop: %s", e)
                await asyncio.sleep(self.poll_interval)

    def stop(self):
        self.running = False

    def _claim_next_job(self) -> str | None:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id FROM job
                   WHERE state = 'queued'
                   ORDER BY updated_at ASC LIMIT 1"""
            )
            row = cursor.fetchone()
            if row:
                job_id = row["id"]
                cursor.execute(
                    """UPDATE job SET state = 'processing', attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    (job_id,),
                )
                return job_id
        return None

    def _complete_job(self, job_id: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE job SET state = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (job_id,),
            )

    def _fail_job(self, job_id: str, error_msg: str):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE job SET state = 'failed', error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                (error_msg, job_id),
            )
