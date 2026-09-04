"""Application startup, shutdown, and retention jobs."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from app import agent, attachments, storage, template_system
from app.core.config import AppSettings

logger = logging.getLogger(__name__)


async def retention_worker(settings: AppSettings) -> None:
    while True:
        await asyncio.sleep(15 * 60)
        try:
            await run_in_threadpool(attachments.cleanup_expired)
            await run_in_threadpool(agent.cleanup_expired_conversations)
            await run_in_threadpool(template_system.cleanup_expired)
            await run_in_threadpool(
                storage.cleanup_expired,
                settings.report_retention_days,
                settings.usage_retention_days,
            )
        except Exception as exc:
            logger.warning("定期数据清理失败: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(retention_worker(app.state.settings))
    try:
        yield
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
