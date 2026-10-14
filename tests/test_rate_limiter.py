import pytest

from src.core.rate_limiter import RateLimiter


class TimeMachine:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def time_machine(monkeypatch):
    tm = TimeMachine()
    monkeypatch.setattr("src.core.rate_limiter.time.time", tm.time)
    return tm


def test_allows_messages_within_limits(time_machine):
    print("\n[test_allows_messages_within_limits]")
    limiter = RateLimiter(per_minute=2, per_hour=5)

    allowed, message = limiter.check("tenant", "user")
    print(f"  1: permitido={allowed}, mensaje={message}")
    assert allowed
    assert message is None

    time_machine.advance(10)
    allowed, message = limiter.check("tenant", "user")
    print(f"  2: permitido={allowed}, mensaje={message}")
    assert allowed
    assert message is None


def test_blocks_minute_limit(time_machine):
    print("\n[test_blocks_minute_limit]")
    limiter = RateLimiter(per_minute=2, per_hour=10)

    allowed, message = limiter.check("tenant", "user")
    print(f"  1: permitido={allowed}, mensaje={message}")
    assert allowed
    allowed, message = limiter.check("tenant", "user")
    print(f"  2: permitido={allowed}, mensaje={message}")
    assert allowed

    allowed, message = limiter.check("tenant", "user")
    print(f"  3: permitido={allowed}, mensaje={message}")
    assert not allowed
    assert "minuto" in message

    time_machine.advance(61)
    allowed, message = limiter.check("tenant", "user")
    print(f"  tras 61s: permitido={allowed}, mensaje={message}")
    assert allowed


def test_blocks_hour_limit(time_machine):
    print("\n[test_blocks_hour_limit]")
    limiter = RateLimiter(per_minute=10, per_hour=2)

    allowed, message = limiter.check("tenant", "user")
    print(f"  1: permitido={allowed}, mensaje={message}")
    assert allowed
    time_machine.advance(15)
    allowed, message = limiter.check("tenant", "user")
    print(f"  2: permitido={allowed}, mensaje={message}")
    assert allowed

    allowed, message = limiter.check("tenant", "user")
    print(f"  3: permitido={allowed}, mensaje={message}")
    assert not allowed
    assert "hora" in message

    time_machine.advance(3601)
    allowed, message = limiter.check("tenant", "user")
    print(f"  tras 3601s: permitido={allowed}, mensaje={message}")
    assert allowed


def test_tenants_are_isolated(time_machine):
    print("\n[test_tenants_are_isolated]")
    limiter = RateLimiter(per_minute=1, per_hour=1)

    allowed, message = limiter.check("tenant-a", "user")
    print(f"  tenant-a 1: permitido={allowed}, mensaje={message}")
    assert allowed

    allowed, message = limiter.check("tenant-b", "user")
    print(f"  tenant-b 1: permitido={allowed}, mensaje={message}")
    assert allowed, "Otro tenant no debería verse afectado"

    allowed, message = limiter.check("tenant-a", "user")
    print(f"  tenant-a 2: permitido={allowed}, mensaje={message}")
    assert not allowed, "El mismo tenant debe seguir limitado"
