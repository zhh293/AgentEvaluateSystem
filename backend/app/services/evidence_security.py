from __future__ import annotations

from typing import Any


SENSITIVE_MARKERS = ("authorization", "api_key", "apikey", "secret", "token", "password", "credential", "cookie")


def redact_evidence(value: Any, secret_values: tuple[str, ...] = ()) -> Any:
    """Recursively redact secrets before evidence reaches judges or storage."""
    secrets = tuple(item for item in secret_values if item)
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in SENSITIVE_MARKERS):
                result[key] = "[REDACTED]"
            else:
                result[key] = redact_evidence(item, secrets)
        return result
    if isinstance(value, list):
        return [redact_evidence(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [redact_evidence(item, secrets) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secrets:
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return value
