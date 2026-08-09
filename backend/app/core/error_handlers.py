import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI):
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        logger.warning(
            "应用异常",
            extra={
                "code": exc.code,
                "message": exc.message,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.error(
            "未处理异常",
            exc_info=exc,
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
        )
