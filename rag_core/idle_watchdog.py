"""
闲置 / 内存感知看门狗 — 让 RAG 服务"不用就退"

设计见 docs/plans/2026-10-31-rag-autostart-design.md

判定逻辑全部在纯函数 should_shutdown() 中，便于单测；
IdleWatchdog 只是很薄的一层壳（记录时间戳 + 读内存 + 调用纯函数）。

退出规则：
  • idle > idle_timeout_sec                      → "idle_timeout"
  • idle > mem_idle_sec 且 free_mb < mem_min_mb  → "memory_pressure"
  • idle_timeout_sec <= 0                        → 完全禁用（纯常驻）
  • mem_min_mb <= 0                              → 仅禁用内存分支
"""
import ctypes
import time
from typing import Callable, Optional, Tuple

__all__ = ["should_shutdown", "read_free_mb", "IdleWatchdog"]


def should_shutdown(
    idle_sec: float,
    free_mb: float,
    *,
    idle_timeout_sec: int,
    mem_idle_sec: int,
    mem_min_mb: int,
) -> Tuple[bool, str]:
    """返回 (是否应退出, 原因)。原因取值："" / "idle_timeout" / "memory_pressure"。"""
    # idle_timeout_sec <= 0 → 完全禁用（调试用，纯常驻）
    if idle_timeout_sec is None or idle_timeout_sec <= 0:
        return (False, "")

    # 1) 正常闲置超时
    if idle_sec > idle_timeout_sec:
        return (True, "idle_timeout")

    # 2) 内存紧张：已闲置一小会儿 + 可用内存不足 → 提前让位
    if mem_min_mb and mem_min_mb > 0 and idle_sec > mem_idle_sec and free_mb < mem_min_mb:
        return (True, "memory_pressure")

    return (False, "")


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def read_free_mb() -> float:
    """系统可用物理内存（MB）。失败时返回 inf —— 宁可不退出，也不误退。"""
    try:
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return float("inf")
        return float(stat.ullAvailPhys) / (1024.0 * 1024.0)
    except Exception:
        # 非 Windows 或 API 不可用
        return float("inf")


class IdleWatchdog:
    """记录"最后活动时间"，判断是否该退出。

    参数：
        idle_timeout_sec: 闲置退出秒数（<=0 禁用）
        mem_idle_sec:     内存分支要求的最小闲置秒数
        mem_min_mb:       可用内存下限（MB，<=0 禁用内存分支）
        free_mb_fn:       读取可用内存的函数（可注入，便于测试）
        clock:            计时器（可注入，便于测试）
    """

    def __init__(
        self,
        *,
        idle_timeout_sec: int = 300,
        mem_idle_sec: int = 60,
        mem_min_mb: int = 400,
        free_mb_fn: Callable[[], float] = read_free_mb,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.idle_timeout_sec = idle_timeout_sec
        self.mem_idle_sec = mem_idle_sec
        self.mem_min_mb = mem_min_mb
        self._free_mb_fn = free_mb_fn
        self._clock = clock
        self._last = clock()

    @property
    def enabled(self) -> bool:
        return bool(self.idle_timeout_sec and self.idle_timeout_sec > 0)

    def touch(self) -> None:
        """记录一次活动（任何 API 请求都该调用）"""
        self._last = self._clock()

    def idle_sec(self) -> float:
        return self._clock() - self._last

    def run_once(self) -> Optional[str]:
        """检查一次。应退出则返回原因字符串，否则 None。"""
        ok, reason = should_shutdown(
            self.idle_sec(),
            self._free_mb_fn(),
            idle_timeout_sec=self.idle_timeout_sec,
            mem_idle_sec=self.mem_idle_sec,
            mem_min_mb=self.mem_min_mb,
        )
        return reason if ok else None
