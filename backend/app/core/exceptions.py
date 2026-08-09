class AppException(Exception):
    """应用基础异常"""

    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationException(AppException):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)


class NotFoundException(AppException):
    def __init__(self, message: str):
        super().__init__(message, code="NOT_FOUND", status_code=404)


class SandboxException(AppException):
    def __init__(self, message: str):
        super().__init__(message, code="SANDBOX_ERROR", status_code=500)


class EvaluationException(AppException):
    def __init__(self, message: str):
        super().__init__(message, code="EVALUATION_ERROR", status_code=500)
