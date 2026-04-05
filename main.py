from __future__ import annotations
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import get_settings
from bot.webhook import router as webhook_router
from bot.telegram_webhook import router as telegram_router
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

    # Auto-register Telegram webhook if token + base_url are configured
    if settings.telegram_bot_token and settings.base_url not in ("http://localhost:8000", ""):
        try:
            from bot.telegram_client import set_webhook, get_me
            bot_info = await get_me()
            bot_name = bot_info.get("result", {}).get("username", "unknown")
            logger.info("Telegram bot: @%s", bot_name)
            tg_webhook_url = f"{settings.base_url.rstrip('/')}/telegram/webhook"
            result = await set_webhook(tg_webhook_url)
            if result.get("ok"):
                logger.info("Telegram webhook registered: %s", tg_webhook_url)
            else:
                logger.warning("Telegram webhook registration failed: %s", result)
        except Exception:
            logger.exception("Could not register Telegram webhook on startup")

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
app.include_router(telegram_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "sarkari-naukri-bot"}


@app.post("/telegram/setup")
async def setup_telegram_webhook():
    """Manually re-register the Telegram webhook. Call this after ngrok restarts."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set in .env"}
    if not settings.base_url or settings.base_url == "http://localhost:8000":
        return {"ok": False, "error": "BASE_URL must be set to a public HTTPS URL (e.g. ngrok URL)"}
    from bot.telegram_client import set_webhook, get_me
    bot_info = await get_me()
    bot_name = bot_info.get("result", {}).get("username", "unknown")
    tg_webhook_url = f"{settings.base_url.rstrip('/')}/telegram/webhook"
    result = await set_webhook(tg_webhook_url)
    return {"bot": f"@{bot_name}", "webhook_url": tg_webhook_url, **result}


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.app_port, reload=True)
