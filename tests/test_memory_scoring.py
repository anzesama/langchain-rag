"""脑启发性记忆评分 —— 纯函数单测（Phase 1 / 验收 V5）

覆盖 `rag_core/memory_scoring.py` 全部纯函数：
- compute_importance()      静态重要性（LUFY 六维的规则版）
- forgetting_decay()        艾宾浩斯软遗忘
- compute_final_score()     综合评分
- update_after_retrieval()  检索命中后的突触强化

⚠️ 半衰期语义（已确认 Q2=A=7 天）：
    `forgetting_decay` 的 `half_life_days` 是**真正的半衰期**——
    经过 1 个半衰期后记忆强度恰好剩 **50%**（`2 ** (-Δ/H)`），
    而非设计草稿里笔误的 `exp(-Δ/H)`（那是 36.8%）。
"""
from datetime import datetime, timedelta

import pytest

from rag_core.memory_scoring import (
    CONSOLIDATE_THRESHOLD,
    DEFAULT_HALF_LIFE_DAYS,
    compute_final_score,
    compute_importance,
    forgetting_decay,
    update_after_retrieval,
)

NOW = datetime(2026, 11, 4, 12, 0, 0)


# ---------------------------------------------------------------- importance

class TestComputeImportance:
    def test_returns_score_in_unit_range(self):
        for text in ["", "短", "a" * 50, "a" * 5000, "重要发现：结论如下"]:
            score = compute_importance(text, "doc.txt")
            assert 0.0 <= score <= 1.0, f"{text[:20]!r} -> {score}"

    def test_is_deterministic(self):
        args = ("关键结论：必须修复 bug", "troubleshooting.md")
        assert compute_importance(*args) == compute_importance(*args)

    def test_very_short_text_is_penalized(self):
        """<50 字多为碎片，应低于同来源的中等长度文本"""
        short = compute_importance("碎片", "doc.txt")
        normal = compute_importance("这是一段长度适中的普通内容。" * 5, "doc.txt")
        assert short < normal

    def test_long_text_is_rewarded(self):
        """长文可能是重要章节"""
        long_text = "普通内容" * 300          # >1000
        medium = "普通内容" * 50              # ~200
        assert compute_importance(long_text, "doc.txt") > compute_importance(medium, "doc.txt")

    @pytest.mark.parametrize("text", [
        "关键结论：这个方案可行",
        "经验总结：踩过的坑",
        "修复了一个 bug",
        "决定采用方案甲",
    ])
    def test_importance_keywords_raise_score(self, text):
        neutral = "今天的天气还不错，适合出门散步。" * 4
        assert compute_importance(text, "doc.txt") > compute_importance(neutral, "doc.txt")
    def test_troubleshooting_source_beats_novel(self):
        body = "这是一段普通内容。" * 5
        ts = compute_importance(body, "troubleshooting.md")
        novel = compute_importance(body, "novel_chapters/ch1.txt")
        plain = compute_importance(body, "misc.txt")
        assert ts > plain > novel

    def test_several_signals_saturate_at_one(self):
        score = compute_importance(
            "重要发现：关键结论 —— 经验总结，修复了 bug 与事故，决定采用方案甲。" * 10,
            "troubleshooting.md",
        )
        assert score == pytest.approx(1.0)

    def test_neutral_content_lands_mid_range(self):
        """普通内容不应被打到 0（否则 importance_bonus 会一律降到 0.5 下限）"""
        score = compute_importance("这是一段普通的说明文字。" * 6, "misc.txt")
        assert 0.2 <= score <= 0.7

    def test_accepts_metadata_kwarg(self):
        body = "普通内容。" * 10
        assert compute_importance(body, "doc.txt", {"memory_type": "semantic"}) == \
            compute_importance(body, "doc.txt")


# ------------------------------------------------------------------- decay

class TestForgettingDecay:
    def test_no_elapsed_time_is_full_strength(self):
        assert forgetting_decay(NOW, NOW, 7.0) == pytest.approx(1.0)

    def test_one_half_life_leaves_half(self):
        """⚠️ 核心语义：half_life_days 是真正的半衰期"""
        d = forgetting_decay(NOW - timedelta(days=7), NOW, 7.0)
        assert d == pytest.approx(0.5)

    def test_two_half_lives_leave_quarter(self):
        d = forgetting_decay(NOW - timedelta(days=14), NOW, 7.0)
        assert d == pytest.approx(0.25)

    def test_longer_half_life_decays_slower(self):
        old = NOW - timedelta(days=7)
        assert forgetting_decay(old, NOW, 30.0) > forgetting_decay(old, NOW, 7.0)

    def test_monotonically_decreasing(self):
        ds = [forgetting_decay(NOW - timedelta(days=n), NOW, 7.0) for n in range(0, 60, 3)]
        assert ds == sorted(ds, reverse=True)

    def test_result_stays_in_unit_range(self):
        for days in [0, 1, 7, 100, 3650]:
            d = forgetting_decay(NOW - timedelta(days=days), NOW, 7.0)
            assert 0.0 <= d <= 1.0

    def test_future_timestamp_is_clamped_to_one(self):
        """时钟漂移不应产生 >1 的加成"""
        assert forgetting_decay(NOW + timedelta(days=3), NOW, 7.0) == pytest.approx(1.0)

    def test_none_means_never_accessed_so_no_penalty(self):
        assert forgetting_decay(None, NOW, 7.0) == pytest.approx(1.0)

    def test_accepts_iso_string(self):
        d = forgetting_decay("2026-10-28T12:00:00", NOW, 7.0)
        assert d == pytest.approx(0.5)

    def test_now_defaults_to_utcnow(self):
        d = forgetting_decay(datetime.utcnow())
        assert d == pytest.approx(1.0, abs=1e-3)

    def test_default_half_life_is_seven_days(self):
        assert DEFAULT_HALF_LIFE_DAYS == 7.0


# ------------------------------------------------------------- final score

class TestComputeFinalScore:
    def test_neutral_inputs_reproduce_similarity_scaled_by_lower_bound(self):
        """importance=0 -> bonus=0.5, count=0 -> bonus=1, decay=1"""
        assert compute_final_score(0.8, 0.0, 1.0, 0) == pytest.approx(0.8 * 0.5)

    def test_max_importance_and_fresh_gives_no_penalty(self):
        assert compute_final_score(0.8, 1.0, 1.0, 0) == pytest.approx(0.8 * 1.0)

    def test_higher_importance_ranks_higher(self):
        a = compute_final_score(0.8, 0.9, 1.0, 0)
        b = compute_final_score(0.8, 0.2, 1.0, 0)
        assert a > b

    def test_decay_lowers_score(self):
        fresh = compute_final_score(0.8, 0.5, 1.0, 0)
        faded = compute_final_score(0.8, 0.5, 0.25, 0)
        assert faded < fresh

    def test_more_accesses_rank_higher_but_capped(self):
        few = compute_final_score(0.8, 0.5, 1.0, 1)
        many = compute_final_score(0.8, 0.5, 1.0, 100)
        assert many > few
        # 访问加成封顶 1.5
        assert compute_final_score(0.8, 0.5, 1.0, 10 ** 6) <= 0.8 * 1.0 * 1.5 + 1e-9

    def test_soft_forgetting_never_deletes(self):
        """长时间未访问只降权，分数仍 > 0（软遗忘铁律）"""
        assert compute_final_score(0.8, 0.5, 1e-9, 0) > 0.0

    def test_disabled_switch_is_handled_by_caller_not_here(self):
        """纯函数不做开关判断：sim=0 -> score=0"""
        assert compute_final_score(0.0, 1.0, 1.0, 99) == pytest.approx(0.0)


# --------------------------------------------------------- retrieval update

class TestUpdateAfterRetrieval:
    def test_increments_count_and_boosts_importance(self):
        count, imp = update_after_retrieval(3, 0.5)
        assert count == 4
        assert imp == pytest.approx(0.5 * 1.05)

    def test_first_retrieval(self):
        assert update_after_retrieval(0, 0.5) == (1, pytest.approx(0.525))

    def test_importance_is_capped_at_one(self):
        count, imp = update_after_retrieval(100, 0.99)
        assert imp == pytest.approx(1.0)
        assert count == 101

    def test_repeated_retrieval_never_exceeds_cap(self):
        imp = 0.9
        for _ in range(50):
            _, imp = update_after_retrieval(0, imp)
        assert imp == pytest.approx(1.0)

    def test_consolidation_threshold_is_three(self):
        assert CONSOLIDATE_THRESHOLD == 3
