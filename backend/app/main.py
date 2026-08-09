from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.error_handlers import register_error_handlers
from app.api.v1 import submissions_router

setup_logging()

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(submissions_router, prefix="/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}
