import uuid

import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError
from app.core.rate_limiter import RateLimiter
from app.core.security import create_access_token, hash_password, verify_password, verify_token


def test_password_hash_and_jwt_round_trip():
    encoded = hash_password("correct horse battery staple")
    assert encoded != "correct horse battery staple"
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)
    user_id = str(uuid.uuid4())
    assert verify_token(create_access_token(user_id))["sub"] == user_id


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    limiter = RateLimiter(max_requests=2, window_seconds=10)
    assert not await limiter.is_rate_limited("u", now=1)
    assert not await limiter.is_rate_limited("u", now=2)
    assert await limiter.is_rate_limited("u", now=3)
    assert not await limiter.is_rate_limited("u", now=20)


@pytest.mark.asyncio
async def test_circuit_breaker_opens_half_opens_and_recovers():
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=10)
    breaker.record_failure(now=0); breaker.record_failure(now=1)
    assert breaker.state == "open"
    assert not breaker.allow_request(now=5)
    assert breaker.allow_request(now=12)
    breaker.record_success()
    assert breaker.state == "closed"
    assert await breaker.call(lambda: 42) == 42
