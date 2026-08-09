from app.api.v1.submissions import router as submissions_router
from app.api.v1.evaluations import router as evaluations_router
from app.api.v1.websocket import router as websocket_router
from app.api.v1.auth import router as auth_router
from app.api.v1.test_cases import router as test_cases_router
from app.api.v1.trace import router as trace_router
from app.api.v1.admin import router as admin_router
from app.api.v1.quality_gates import router as quality_gates_router

__all__ = ["submissions_router", "evaluations_router", "websocket_router", "auth_router", "test_cases_router", "trace_router", "admin_router", "quality_gates_router"]
