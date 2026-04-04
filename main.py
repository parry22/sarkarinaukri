from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import get_settings
from bot.webhook import router as webhook_router
from bot.whatsapp_client import close_http_client
from scraping.scheduler.cron_manager import setup_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    logger.info(f"Starting Sarkari Naukri Alert Bot ({settings.app_env})")

    if settings.app_env != "testing":
        scheduler = setup_scheduler()
        logger.info("Scraping scheduler started")

    yield

    # Shutdown
    if settings.app_env != "testing":
        shutdown_scheduler()
        logger.info("Scheduler shut down")

    await close_http_client()
    logger.info("HTTP client closed")


settings = get_settings()

_docs_kwargs: dict = {}
if settings.app_env != "development":
    _docs_kwargs = {"docs_url": None, "redoc_url": None, "openapi_url": None}

app = FastAPI(
    title="Sarkari Naukri Alert Bot",
    description="Personalized government job alerts via WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
    **_docs_kwargs,
)

app.include_router(webhook_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "sarkari-naukri-bot"}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=True)
