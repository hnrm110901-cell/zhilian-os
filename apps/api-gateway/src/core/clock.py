"""
时间抽象层
IClock / SystemClock / MockClock

目的：
- 统一全库的时间获取入口，消除裸调用 datetime.now() / datetime.utcnow()
- 支持测试时注入任意时间点（MockClock），彻底解决凌晨关账等边界场景的测试难题
- 为跨时区多门店场景提供统一的 UTC 基准

用法：
    # 生产代码
    from src.core.clock import get_clock
    now = get_clock().now()          # 带时区的 UTC datetime
    today = get_clock().today()      # 本地营业日 date（Asia/Shanghai）

    # 测试代码
    from src.core.clock import MockClock, set_clock
    mock = MockClock(datetime(2024, 1, 1, 22, 30, tzinfo=timezone.utc))
    set_clock(mock)
    # ... 执行被测逻辑 ...
    set_clock(None)  # 还原
"""

import abc
from datetime import datetime, date, timezone, timedelta
from typing import Optional
import os

# 上海时区偏移（UTC+8），不依赖 pytz/zoneinfo 保持零额外依赖
_SHANGHAI_OFFSET = timedelta(hours=int(os.getenv("BUSINESS_TZ_OFFSET_HOURS", "8")))
_SHANGHAI_TZ = timezone(_SHANGHAI_OFFSET)


class IClock(abc.ABC):
    """时间提供者接口"""

    @abc.abstractmethod
    def now(self) -> datetime:
        """返回当前 UTC 时间（带时区信息）"""
        ...

    def now_local(self) -> datetime:
        """返回当前本地时间（Asia/Shanghai，UTC+8）"""
        return self.now().astimezone(_SHANGHAI_TZ)

    def today(self) -> date:
        """返回本地营业日（Asia/Shanghai）"""
        return self.now_local().date()

    def utcnow(self) -> datetime:
        """兼容旧代码：返回不带时区的 UTC datetime（逐步迁移用）"""
        return self.now().replace(tzinfo=None)


class SystemClock(IClock):
    """生产环境时钟：读取系统真实时间"""

    def now(self) -> datetime:
        return datetime.now(tz=timezone.utc)


class MockClock(IClock):
    """测试时钟：固定或可步进的时间"""

    def __init__(self, fixed_time: Optional[datetime] = None):
        if fixed_time is None:
            fixed_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        # 确保带时区
        if fixed_time.tzinfo is None:
            fixed_time = fixed_time.replace(tzinfo=timezone.utc)
        self._time = fixed_time

    def now(self) -> datetime:
        return self._time

    def set(self, dt: datetime) -> None:
        """直接设置时间"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        self._time = dt

    def advance(self, **kwargs) -> None:
        """步进时间，参数同 timedelta（hours=1, minutes=30 等）"""
        self._time += timedelta(**kwargs)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_clock: IClock = SystemClock()


def get_clock() -> IClock:
    """获取当前全局时钟实例"""
    return _clock


def set_clock(clock: Optional[IClock]) -> None:
    """替换全局时钟（测试用）；传 None 还原为 SystemClock"""
    global _clock
    _clock = clock if clock is not None else SystemClock()


# ---------------------------------------------------------------------------
# 便捷函数（直接替换裸调用）
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    """当前 UTC 时间（带时区）"""
    return _clock.now()


def now_local() -> datetime:
    """当前本地时间（Asia/Shanghai）"""
    return _clock.now_local()


def today_local() -> date:
    """当前本地营业日"""
    return _clock.today()


def utcnow_naive() -> datetime:
    """不带时区的 UTC datetime，用于兼容旧代码逐步迁移"""
    return _clock.utcnow()
