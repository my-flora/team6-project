"""测试公用工具。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


class FakeClock:
    """可推进的假时钟，用来验证时间盒与 24 小时会签超时。"""

    def __init__(self, start: datetime | None = None) -> None:
        self.now = start or datetime(2026, 11, 14, 9, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: int = 0, minutes: int = 0, hours: int = 0) -> None:
        self.now += timedelta(seconds=seconds, minutes=minutes, hours=hours)
