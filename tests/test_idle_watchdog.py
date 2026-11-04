import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ==================== should_shutdown（纯函数）====================

def test_no_shutdown_when_active():
    from rag_core.idle_watchdog import should_shutdown
    ok, reason = should_shutdown(10, 1000, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400)
    assert ok is False
    assert reason == ""


def test_shutdown_on_idle_timeout():
    from rag_core.idle_watchdog import should_shutdown
    ok, reason = should_shutdown(301, 1000, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400)
    assert ok is True
    assert reason == "idle_timeout"


def test_shutdown_on_memory_pressure():
    from rag_core.idle_watchdog import should_shutdown
    ok, reason = should_shutdown(61, 100, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400)
    assert ok is True
    assert reason == "memory_pressure"


def test_no_memory_shutdown_before_mem_idle():
    from rag_core.idle_watchdog import should_shutdown
    ok, reason = should_shutdown(30, 100, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400)
    assert ok is False
    assert reason == ""


def test_idle_timeout_zero_disables_everything():
    """RAG_IDLE_TIMEOUT_SEC=0 → 完全禁用退出（纯常驻），内存分支也不触发"""
    from rag_core.idle_watchdog import should_shutdown
    ok, reason = should_shutdown(9999, 1, idle_timeout_sec=0, mem_idle_sec=60, mem_min_mb=400)
    assert ok is False
    assert reason == ""


def test_memory_branch_disabled_when_mem_min_zero():
    from rag_core.idle_watchdog import should_shutdown
    # mem_min_mb=0 → 内存分支禁用，但 idle 超时仍生效
    ok, reason = should_shutdown(9999, 1, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=0)
    assert ok is True
    assert reason == "idle_timeout"
    # 且未超时时不因内存退出
    ok2, reason2 = should_shutdown(10, 1, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=0)
    assert ok2 is False
    assert reason2 == ""


def test_idle_timeout_boundary_is_strict():
    """idle == timeout 不算超时（严格大于）"""
    from rag_core.idle_watchdog import should_shutdown
    ok, _ = should_shutdown(300, 1000, idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400)
    assert ok is False


# ==================== read_free_mb ====================

def test_read_free_mb_returns_positive_number():
    from rag_core.idle_watchdog import read_free_mb
    v = read_free_mb()
    assert isinstance(v, float)
    assert v > 0


# ==================== IdleWatchdog ====================

class _Clock:
    def __init__(self, t=0.0):
        self.t = t
    def __call__(self):
        return self.t


def test_watchdog_touch_resets_idle():
    from rag_core.idle_watchdog import IdleWatchdog
    c = _Clock(0.0)
    wd = IdleWatchdog(idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=0,
                      free_mb_fn=lambda: 1000.0, clock=c)
    c.t = 50.0
    assert wd.idle_sec() == 50.0
    wd.touch()
    assert wd.idle_sec() == 0.0


def test_run_once_returns_none_while_active_then_reason():
    from rag_core.idle_watchdog import IdleWatchdog
    c = _Clock(0.0)
    wd = IdleWatchdog(idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=0,
                      free_mb_fn=lambda: 1000.0, clock=c)
    assert wd.run_once() is None
    c.t = 301.0
    assert wd.run_once() == "idle_timeout"


def test_run_once_uses_injected_free_mb():
    from rag_core.idle_watchdog import IdleWatchdog
    c = _Clock(100.0)
    wd = IdleWatchdog(idle_timeout_sec=300, mem_idle_sec=60, mem_min_mb=400,
                      free_mb_fn=lambda: 50.0, clock=c)
    wd.touch()          # last = 100
    c.t = 161.0         # idle = 61 > mem_idle 60, free 50 < 400
    assert wd.run_once() == "memory_pressure"


def test_run_once_disabled_when_timeout_zero():
    from rag_core.idle_watchdog import IdleWatchdog
    c = _Clock(0.0)
    wd = IdleWatchdog(idle_timeout_sec=0, mem_idle_sec=60, mem_min_mb=400,
                      free_mb_fn=lambda: 1.0, clock=c)
    c.t = 999999.0
    assert wd.run_once() is None
