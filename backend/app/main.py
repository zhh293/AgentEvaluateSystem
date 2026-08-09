import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response
import redis.asyncio as redis
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.error_handlers import register_error_handlers
from app.api.v1 import admin_router, auth_router, case_sets_router, evaluations_router, quality_gates_router, submissions_router, test_cases_router, trace_router, websocket_router
from app.core.rate_limiter import RateLimiter
from app.core.security import verify_token
from app.core.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.core.audit import record_audit

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

rate_limiter = RateLimiter(redis.from_url(settings.REDIS_URL, decode_responses=True), max_requests=120, window_seconds=60)


@app.middleware("http")
async def gateway_middleware(request: Request, call_next):
    started = time.perf_counter()
    authorization = request.headers.get("authorization", "")
    subject = None
    if authorization.lower().startswith("bearer "):
        try:
            subject = verify_token(authorization[7:]).get("sub")
        except Exception:
            pass
    key = f"rate:{subject or (request.client.host if request.client else 'unknown')}"
    if request.url.path != "/health" and await rate_limiter.is_rate_limited(key):
        response = JSONResponse(status_code=429, content={"code": "RATE_LIMITED", "message": "Too Many Requests"})
    else:
        response = await call_next(request)
    route = request.scope.get("route")
    metric_path = getattr(route, "path", request.url.path)
    elapsed_seconds = time.perf_counter() - started
    HTTP_REQUESTS.labels(request.method, metric_path, str(response.status_code)).inc()
    HTTP_DURATION.labels(request.method, metric_path).observe(elapsed_seconds)
    await record_audit(request, response.status_code, (time.perf_counter() - started) * 1000, subject)
    return response

app.include_router(submissions_router, prefix="/v1")
app.include_router(evaluations_router, prefix="/v1")
app.include_router(websocket_router, prefix="/v1")
app.include_router(auth_router, prefix="/v1")
app.include_router(test_cases_router, prefix="/v1")
app.include_router(trace_router, prefix="/v1")
app.include_router(admin_router, prefix="/v1")
app.include_router(quality_gates_router, prefix="/v1")
app.include_router(case_sets_router, prefix="/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
